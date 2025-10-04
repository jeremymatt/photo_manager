"""
File scanner for discovering and processing image files.
Handles directory scanning, auto-tagging, and database updates.
"""

import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Tuple

from PIL import Image
from sqlalchemy.orm import Session

from ..database.models import Image as ImageModel, get_or_create_tag
from ..database.database_manager import DatabaseManager
from ..config.config_manager import AutoTagTemplate
from ..utils.exif_reader import extract_datetime_from_exif, extract_location_from_exif
from ..utils.filename_parser import extract_datetime_from_filename
from .duplicate_detector import DuplicateDetector


def is_image_file(file_path: str) -> bool:
    """
    Check if file is an image using PIL and file extension.
    
    Args:
        file_path: Path to file
        
    Returns:
        True if file is an image
    """
    try:
        # First check extension for speed
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp'}
        extension = Path(file_path).suffix.lower()
        
        print(f"      PIL check: extension='{extension}', in supported={extension in image_extensions}")
        
        if extension not in image_extensions:
            return False
        
        # Then verify with PIL - but be less strict
        try:
            with Image.open(file_path) as img:
                width, height = img.size
                print(f"      PIL opened successfully: {width}x{height}")
                return width > 0 and height > 0
        except Exception as e:
            print(f"      PIL failed to open: {e}")
            return False
            
    except Exception as e:
        print(f"      Error in is_image_file: {e}")
        return False


class FileScanner:
    """Scans directories for images and processes them."""
    
    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]):
        """
        Initialize file scanner.
        
        Args:
            db_manager: Database manager instance
            config: Configuration dictionary
        """
        self.db_manager = db_manager
        self.config = config
        self.scan_config = config.get('file_scanning', {})
        
        # Supported file formats
        self.supported_formats = set(self.scan_config.get('supported_formats', [
            'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'tif', 'webp'
        ]))
        
        # Formats to skip
        self.skip_formats = set(self.scan_config.get('video_formats_to_skip', [
            'mp4', 'avi', 'wmv', 'mov', 'flv', 'mpg', 'mpeg'
        ]))
        
        # File size limits
        self.max_file_size = self.scan_config.get('max_file_size_mb', 500) * 1024 * 1024
        
        # Initialize duplicate detector
        self.duplicate_detector = DuplicateDetector(config)
        
        # Progress tracking
        self.progress_callback = None
        self.stop_scanning = threading.Event()
    
    def scan_directory(self, directory_path: str, 
                      auto_tag_template: Optional[AutoTagTemplate] = None,
                      progress_callback: Optional[Callable] = None) -> Tuple[int, int, List[str]]:
        """
        Scan directory for images and add to database.
        
        Args:
            directory_path: Path to directory to scan
            auto_tag_template: Optional auto-tagging template
            progress_callback: Function to call with progress (processed, total, current_file)
            
        Returns:
            Tuple of (images_added, images_skipped, error_files)
        """
        self.progress_callback = progress_callback
        self.stop_scanning.clear()
        
        # Find all image files
        image_files = self._find_image_files(directory_path)
        
        if progress_callback:
            progress_callback(0, len(image_files), "Starting scan...")
        
        # Start background hash processing
        self.duplicate_detector.start_background_processing(self._hash_calculated_callback)
        
        images_added = 0
        images_skipped = 0
        error_files = []
        
        try:
            with self.db_manager.get_session() as session:
                for i, file_path in enumerate(image_files):
                    if self.stop_scanning.is_set():
                        break
                    
                    if progress_callback:
                        progress_callback(i, len(image_files), os.path.basename(file_path))
                    
                    result = self._process_image_file(session, file_path, directory_path, auto_tag_template)
                    
                    if result == 'added':
                        images_added += 1
                    elif result == 'skipped':
                        images_skipped += 1
                    elif result == 'error':
                        error_files.append(file_path)
                
                # Mark directory as scanned
                self.db_manager.mark_directory_scanned(
                    session, directory_path, 
                    template_path=getattr(auto_tag_template, 'template_path', None),
                    image_count=images_added
                )
                
                session.commit()
        
        except Exception as e:
            print(f"Error during directory scan: {e}")
            session.rollback()
        
        finally:
            self.duplicate_detector.stop_background_processing()
            
            if progress_callback:
                progress_callback(len(image_files), len(image_files), "Scan complete")
        
        return images_added, images_skipped, error_files
    
    def _find_image_files(self, directory_path: str) -> List[str]:
        """
        Recursively find all image files in directory.
        
        Args:
            directory_path: Root directory to scan
            
        Returns:
            List of absolute paths to image files
        """
        image_files = []
        include_subdirs = self.scan_config.get('include_subdirectories', True)
        ignore_hidden = self.scan_config.get('ignore_hidden_files', True)
        ignore_patterns = self.scan_config.get('ignore_patterns', [])
        
        print(f"Scanning directory: {directory_path}")
        print(f"Include subdirectories: {include_subdirs}")
        
        try:
            if include_subdirs:
                for root, dirs, files in os.walk(directory_path):
                    print(f"Checking directory: {root} - {len(files)} files")
                    
                    # Filter out hidden directories if configured
                    if ignore_hidden:
                        dirs[:] = [d for d in dirs if not d.startswith('.')]
                    
                    for file in files:
                        file_path = os.path.join(root, file)
                        print(f"Checking file: {file}")
                        
                        if self._is_valid_image_file(file_path, ignore_patterns, ignore_hidden):
                            image_files.append(file_path)
                            print(f"  -> Valid image: {file}")
                        else:
                            print(f"  -> Skipped: {file}")
            else:
                # Single directory only
                files = os.listdir(directory_path)
                print(f"Single directory scan: {len(files)} files")
                
                for file in files:
                    file_path = os.path.join(directory_path, file)
                    if (os.path.isfile(file_path) and 
                        self._is_valid_image_file(file_path, ignore_patterns, ignore_hidden)):
                        image_files.append(file_path)
        
        except Exception as e:
            print(f"Error finding image files: {e}")
        
        print(f"Found {len(image_files)} total image files")
        return sorted(image_files)
    
    def _is_valid_image_file(self, file_path: str, ignore_patterns: List[str], ignore_hidden: bool) -> bool:
        """
        Check if file is a valid image file to process.
        
        Args:
            file_path: Path to file
            ignore_patterns: List of patterns to ignore
            ignore_hidden: Whether to ignore hidden files
            
        Returns:
            True if file should be processed
        """
        try:
            filename = os.path.basename(file_path)
            
            # Check if hidden file
            if ignore_hidden and filename.startswith('.'):
                return False
            
            # Check ignore patterns
            for pattern in ignore_patterns:
                if re.match(pattern.replace('*', '.*'), filename):
                    return False
            
            # Check file size
            if os.path.getsize(file_path) > self.max_file_size:
                return False
            
            # Check file extension
            extension = Path(file_path).suffix.lower().lstrip('.')
            if extension in self.skip_formats:
                return False
            
            # Verify it's actually an image
            img_type = Image.open(file_path)
            return img_type is not None
            
        except Exception as e:
            print(f"Error validating file {file_path}: {e}")
            return False
    
    def _process_image_file(self, session: Session, file_path: str, base_directory: str,
                           auto_tag_template: Optional[AutoTagTemplate]) -> str:
        """
        Process a single image file.
        
        Args:
            session: Database session
            file_path: Path to image file
            base_directory: Base directory being scanned
            auto_tag_template: Auto-tagging template
            
        Returns:
            'added', 'skipped', or 'error'
        """
        try:
            # Check if already in database
            existing = session.query(ImageModel).filter_by(file_path=file_path).first()
            if existing:
                return 'skipped'
            
            # Try to load image to get basic metadata
            try:
                with Image.open(file_path) as img:
                    width, height = img.size
                    file_size = os.path.getsize(file_path)
                    
                    # Extract EXIF data
                    exif_datetime = extract_datetime_from_exif(img)
                    exif_location = extract_location_from_exif(img)
                    
            except Exception as img_error:
                # Image is corrupt, but still add to database for tracking
                width, height = 0, 0
                file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                exif_datetime = None
                exif_location = {}
            
            # Try to extract date from filename if no EXIF date
            date_taken = exif_datetime
            if not date_taken:
                date_taken = extract_datetime_from_filename(file_path)
            
            # Create image record
            image = ImageModel(
                file_path=file_path,
                filename=os.path.basename(file_path),
                width=width,
                height=height,
                file_size=file_size,
                date_taken=date_taken,
                location_lat=exif_location.get('latitude'),
                location_lng=exif_location.get('longitude'), 
                location_name=exif_location.get('location_name'),
                is_corrupt=(width == 0),
                load_error=str(img_error) if 'img_error' in locals() else None
            )
            
            session.add(image)
            session.flush()  # Get ID
            
            # Apply auto-tags if template provided
            if auto_tag_template:
                self._apply_auto_tags(session, image, file_path, base_directory, auto_tag_template)
            
            # Queue for hash calculation (if not corrupt)
            if not image.is_corrupt:
                self.duplicate_detector.queue_image_for_hashing(file_path)
            
            return 'added'
            
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            return 'error'
    
    def _apply_auto_tags(self, session: Session, image: ImageModel, file_path: str,
                        base_directory: str, template: AutoTagTemplate):
        """
        Apply auto-tags to an image based on template.
        
        Args:
            session: Database session
            image: Image model instance
            file_path: Full path to image file
            base_directory: Base directory being scanned
            template: Auto-tagging template
        """
        try:
            # Apply fixed tags (applied to ALL images in this import)
            if template.has_fixed_tags():
                fixed_tags = template.get_fixed_tags()
                for category, tag_names in fixed_tags.items():
                    for tag_name in tag_names:
                        self.db_manager.add_tag_to_image(session, image, category, tag_name)
            
            # Apply pattern-based tags
            if template.has_pattern_matching():
                pattern_tags = template.extract_pattern_tags(file_path, base_directory)
                for category, tag_names in pattern_tags.items():
                    for tag_name in tag_names:
                        self.db_manager.add_tag_to_image(session, image, category, tag_name)
                        
        except Exception as e:
            print(f"Error applying auto-tags to {file_path}: {e}")
    
    def _hash_calculated_callback(self, file_path: str, hashes: Dict[str, str]):
        """
        Callback when hash calculation is complete.
        
        Args:
            file_path: Path to image file
            hashes: Dictionary of calculated hashes
        """
        try:
            with self.db_manager.get_session() as session:
                image = session.query(ImageModel).filter_by(file_path=file_path).first()
                if image:
                    # Update hash fields
                    image.phash = hashes.get('phash')
                    image.dhash = hashes.get('dhash')
                    session.commit()
                    
        except Exception as e:
            print(f"Error updating hashes for {file_path}: {e}")
    
    def rescan_directory(self, directory_path: str, 
                        auto_tag_template: Optional[AutoTagTemplate] = None,
                        remove_missing: bool = False,
                        progress_callback: Optional[Callable] = None) -> Tuple[int, int, int]:
        """
        Rescan directory and update database.
        
        Args:
            directory_path: Directory to rescan
            auto_tag_template: Auto-tagging template
            remove_missing: Whether to remove missing files from database
            progress_callback: Progress callback function
            
        Returns:
            Tuple of (added, updated, removed)
        """
        try:
            with self.db_manager.get_session() as session:
                # Get existing images in this directory
                existing_images = session.query(ImageModel).filter(
                    ImageModel.file_path.like(f"{directory_path}%")
                ).all()
                
                existing_paths = {img.file_path for img in existing_images}
                
                # Find current files
                current_files = set(self._find_image_files(directory_path))
                
                added = 0
                updated = 0
                removed = 0
                
                # Add new files
                new_files = current_files - existing_paths
                for file_path in new_files:
                    result = self._process_image_file(session, file_path, directory_path, auto_tag_template)
                    if result == 'added':
                        added += 1
                
                # Remove missing files if requested
                if remove_missing:
                    missing_files = existing_paths - current_files
                    for image in existing_images:
                        if image.file_path in missing_files:
                            session.delete(image)
                            removed += 1
                
                session.commit()
                return added, updated, removed
                
        except Exception as e:
            print(f"Error rescanning directory: {e}")
            return 0, 0, 0
    
    def stop_scan(self):
        """Stop the current scanning operation."""
        self.stop_scanning.set()
        self.duplicate_detector.stop_background_processing()


class DirectoryWatcher:
    """Watch directory for changes and update database accordingly."""
    
    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]):
        """Initialize directory watcher."""
        self.db_manager = db_manager
        self.config = config
        self.watched_directories = {}
        self.watch_thread = None
        self.stop_watching = threading.Event()
    
    def start_watching(self, directories: List[str]):
        """
        Start watching directories for changes.
        
        Args:
            directories: List of directory paths to watch
        """
        # TODO: Implement file system watching
        # Could use watchdog library for cross-platform file watching
        # For now, this is a placeholder for future enhancement
        pass
    
    def stop_watching(self):
        """Stop watching directories."""
        self.stop_watching.set()
        if self.watch_thread:
            self.watch_thread.join()


def validate_directory(directory_path: str) -> Tuple[bool, str]:
    """
    Validate that a directory is suitable for scanning.
    
    Args:
        directory_path: Path to directory
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        if not os.path.exists(directory_path):
            return False, "Directory does not exist"
        
        if not os.path.isdir(directory_path):
            return False, "Path is not a directory"
        
        if not os.access(directory_path, os.R_OK):
            return False, "Directory is not readable"
        
        return True, ""
        
    except Exception as e:
        return False, f"Error validating directory: {e}"


def estimate_scan_time(directory_path: str) -> Tuple[int, str]:
    """
    Estimate scan time based on number of files.
    
    Args:
        directory_path: Directory to estimate for
        
    Returns:
        Tuple of (estimated_files, time_estimate_string)
    """
    try:
        file_count = 0
        for root, dirs, files in os.walk(directory_path):
            file_count += len([f for f in files if not f.startswith('.')])
        
        # Rough estimate: 10-20 files per second depending on file size and system
        estimated_seconds = file_count / 15
        
        if estimated_seconds < 60:
            time_str = f"{int(estimated_seconds)} seconds"
        elif estimated_seconds < 3600:
            time_str = f"{int(estimated_seconds / 60)} minutes"
        else:
            time_str = f"{int(estimated_seconds / 3600)} hours"
        
        return file_count, time_str
        
    except Exception as e:
        print(f"Error estimating scan time: {e}")
        return 0, "unknown"