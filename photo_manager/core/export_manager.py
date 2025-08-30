"""
Export manager for copying/moving images with tag-based queries.
Handles export preview, directory structure creation, and database subset export.
"""

import os
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
from sqlalchemy.orm import Session

from ..database.models import Image, Tag, ImageTag, Directory, TAG_CATEGORIES
from ..database.database_manager import DatabaseManager, create_database
from .tag_manager import TagManager


class ExportManager:
    """Manages export operations with preview and database export capabilities."""
    
    def __init__(self, db_manager: DatabaseManager, tag_manager: TagManager, config: Dict[str, Any]):
        """
        Initialize export manager.
        
        Args:
            db_manager: Database manager instance
            tag_manager: Tag manager instance
            config: Configuration dictionary
        """
        self.db_manager = db_manager
        self.tag_manager = tag_manager
        self.config = config.get('export', {})
        
    def preview_export(self, session: Session, query: str, structure_template: str, 
                      export_path: str) -> Dict[str, Any]:
        """
        Preview what an export operation would do.
        
        Args:
            session: Database session
            query: Tag-based query string
            structure_template: Directory structure template
            export_path: Root export directory
            
        Returns:
            Dictionary with preview information
        """
        try:
            # Get matching images
            images = self.tag_manager.get_images_by_query(session, query)
            
            if not images:
                return {
                    'total_images': 0,
                    'directories': {},
                    'conflicts': [],
                    'errors': []
                }
            
            # Calculate target paths for each image
            target_mapping = {}
            directory_counts = defaultdict(int)
            conflicts = []
            errors = []
            
            for image in images:
                try:
                    target_dir = self._generate_target_directory(session, image, structure_template)
                    target_path = os.path.join(export_path, target_dir, image.filename)
                    
                    target_mapping[image.file_path] = target_path
                    directory_counts[os.path.join(export_path, target_dir)] += 1
                    
                    # Check for filename conflicts
                    if target_path in target_mapping.values():
                        conflicts.append({
                            'filename': image.filename,
                            'target_path': target_path,
                            'source_images': [img.file_path for img in images if 
                                            os.path.join(export_path, 
                                                       self._generate_target_directory(session, img, structure_template), 
                                                       img.filename) == target_path]
                        })
                
                except Exception as e:
                    errors.append({
                        'image': image.file_path,
                        'error': str(e)
                    })
            
            return {
                'total_images': len(images),
                'target_mapping': target_mapping,
                'directories': dict(directory_counts),
                'conflicts': conflicts,
                'errors': errors,
                'estimated_size_mb': sum(img.file_size for img in images) / (1024 * 1024)
            }
            
        except Exception as e:
            print(f"Error previewing export: {e}")
            return {'total_images': 0, 'directories': {}, 'conflicts': [], 'errors': [str(e)]}
    
    def export_images(self, session: Session, query: str, export_path: str,
                     structure_template: str, operation: str = 'copy',
                     export_database: bool = False,
                     progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        Export images based on query.
        
        Args:
            session: Database session
            query: Tag-based query string
            export_path: Root export directory
            structure_template: Directory structure template
            operation: 'copy' or 'move'
            export_database: Whether to create subset database
            progress_callback: Progress callback function
            
        Returns:
            Dictionary with export results
        """
        try:
            # Get preview first
            preview = self.preview_export(session, query, structure_template, export_path)
            
            if preview['total_images'] == 0:
                return {'success': False, 'message': 'No images match query'}
            
            images = self.tag_manager.get_images_by_query(session, query)
            exported_count = 0
            errors = []
            
            # Create export directory
            os.makedirs(export_path, exist_ok=True)
            
            for i, image in enumerate(images):
                if progress_callback:
                    progress_callback(i, len(images), image.filename)
                
                try:
                    result = self._export_single_image(
                        session, image, export_path, structure_template, operation
                    )
                    
                    if result['success']:
                        exported_count += 1
                    else:
                        errors.append({
                            'image': image.file_path,
                            'error': result['error']
                        })
                
                except Exception as e:
                    errors.append({
                        'image': image.file_path,
                        'error': str(e)
                    })
            
            # Create subset database if requested
            subset_db_path = None
            if export_database:
                subset_db_path = self._create_subset_database(
                    session, images, export_path, structure_template
                )
            
            # If moving files, commit database changes
            if operation == 'move':
                session.commit()
            
            result = {
                'success': True,
                'exported_count': exported_count,
                'total_images': len(images),
                'errors': errors,
                'subset_database': subset_db_path
            }
            
            if progress_callback:
                progress_callback(len(images), len(images), f"Export complete: {exported_count} images")
            
            return result
            
        except Exception as e:
            session.rollback()
            print(f"Error during export: {e}")
            return {'success': False, 'message': str(e)}
    
    def _export_single_image(self, session: Session, image: Image, export_path: str,
                           structure_template: str, operation: str) -> Dict[str, Any]:
        """Export a single image file."""
        try:
            # Generate target directory
            target_dir = self._generate_target_directory(session, image, structure_template)
            full_target_dir = os.path.join(export_path, target_dir)
            
            # Create target directory
            os.makedirs(full_target_dir, exist_ok=True)
            
            # Handle filename conflicts
            target_filename = image.filename
            target_path = os.path.join(full_target_dir, target_filename)
            
            counter = 1
            while os.path.exists(target_path):
                name, ext = os.path.splitext(image.filename)
                target_filename = f"{name}_{counter}{ext}"
                target_path = os.path.join(full_target_dir, target_filename)
                counter += 1
            
            # Perform copy or move
            if operation == 'copy':
                shutil.copy2(image.file_path, target_path)
            elif operation == 'move':
                shutil.move(image.file_path, target_path)
                # Update database with new path
                image.file_path = target_path
                image.filename = target_filename
            else:
                return {'success': False, 'error': f'Invalid operation: {operation}'}
            
            return {'success': True, 'target_path': target_path}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _generate_target_directory(self, session: Session, image: Image, template: str) -> str:
        """
        Generate target directory path based on template.
        
        Args:
            session: Database session
            image: Image object
            template: Directory structure template
            
        Returns:
            Relative directory path
        """
        try:
            # Get image tags
            tags = self.db_manager.get_image_tags(session, image)
            
            # Replace template variables
            result = template
            
            # Date-based replacements
            if image.date_taken:
                result = result.replace('{year}', str(image.date_taken.year))
                result = result.replace('{month}', f"{image.date_taken.month:02d}")
                result = result.replace('{day}', f"{image.date_taken.day:02d}")
                result = result.replace('{date}', image.date_taken.strftime("%Y-%m-%d"))
            else:
                result = result.replace('{year}', 'unknown_date')
                result = result.replace('{month}', 'unknown_date')
                result = result.replace('{day}', 'unknown_date')
                result = result.replace('{date}', 'unknown_date')
            
            # Tag-based replacements
            for category in TAG_CATEGORIES:
                placeholder = '{' + category.replace('_tags', '') + '_tag}'
                
                if category in tags and tags[category]:
                    # Handle multiple tags by joining with underscore
                    tag_value = '_'.join(tags[category])
                    result = result.replace(placeholder, tag_value)
                else:
                    # Handle missing tags
                    if self.config.get('handle_no_tags') == 'other_folder':
                        result = result.replace(placeholder, 'other')
                    else:
                        result = result.replace(placeholder, 'untagged')
            
            # Handle multiple matching categories (e.g., birthday + vacation)
            if self.config.get('collision_resolution') == 'combine_tags':
                # This is handled above by joining tag names
                pass
            
            # Photographer replacement
            if image.photographer:
                result = result.replace('{photographer}', image.photographer)
            else:
                result = result.replace('{photographer}', 'unknown_photographer')
            
            # Clean up path (remove invalid characters, normalize separators)
            result = self._sanitize_path(result)
            
            return result
            
        except Exception as e:
            print(f"Error generating target directory for {image.filename}: {e}")
            return 'export_error'
    
    def _sanitize_path(self, path: str) -> str:
        """
        Sanitize path for cross-platform compatibility.
        
        Args:
            path: Raw path string
            
        Returns:
            Sanitized path string
        """
        # Replace invalid characters
        invalid_chars = '<>:"|?*'
        for char in invalid_chars:
            path = path.replace(char, '_')
        
        # Normalize separators
        path = path.replace('\\', '/')
        
        # Remove leading/trailing slashes and spaces
        path = path.strip('/ ')
        
        # Replace multiple consecutive separators
        path = re.sub(r'/+', '/', path)
        
        return path
    
    def _create_subset_database(self, session: Session, images: List[Image], 
                              export_path: str, structure_template: str) -> str:
        """
        Create a subset database containing only exported images.
        
        Args:
            session: Source database session
            images: List of exported images
            export_path: Export directory path
            structure_template: Directory structure template
            
        Returns:
            Path to created subset database
        """
        try:
            # Create subset database
            subset_db_path = os.path.join(export_path, '.photo_manager.db')
            
            if not create_database(subset_db_path):
                raise Exception("Failed to create subset database")
            
            # Create new database manager for subset
            subset_db_config = {
                'type': 'sqlite',
                'path': subset_db_path
            }
            subset_db_manager = DatabaseManager(subset_db_config)
            subset_db_manager.initialize_connection()
            
            with subset_db_manager.get_session() as subset_session:
                # Copy images with updated paths
                for image in images:
                    # Calculate new relative path
                    target_dir = self._generate_target_directory(session, image, structure_template)
                    new_file_path = os.path.join(export_path, target_dir, image.filename)
                    
                    # Create new image record
                    new_image = Image(
                        file_path=new_file_path,
                        filename=image.filename,
                        phash=image.phash,
                        dhash=image.dhash,
                        file_size=image.file_size,
                        width=image.width,
                        height=image.height,
                        date_taken=image.date_taken,
                        date_added=datetime.utcnow(),
                        photographer=image.photographer,
                        location_lat=image.location_lat,
                        location_lng=image.location_lng,
                        location_name=image.location_name,
                        tags_reviewed=image.tags_reviewed,
                        is_corrupt=image.is_corrupt,
                        load_error=image.load_error
                    )
                    
                    subset_session.add(new_image)
                    subset_session.flush()
                    
                    # Copy tags
                    for image_tag in image.tags:
                        # Get or create tag in subset database
                        tag = subset_session.query(Tag).filter_by(
                            category=image_tag.tag.category,
                            name=image_tag.tag.name
                        ).first()
                        
                        if not tag:
                            tag = Tag(
                                category=image_tag.tag.category,
                                name=image_tag.tag.name
                            )
                            subset_session.add(tag)
                            subset_session.flush()
                        
                        # Create image-tag relationship
                        new_image_tag = ImageTag(
                            image_id=new_image.id,
                            tag_id=tag.id,
                            date_applied=image_tag.date_applied
                        )
                        subset_session.add(new_image_tag)
                
                # Mark export directory as scanned
                subset_db_manager.mark_directory_scanned(
                    subset_session,
                    export_path,
                    template_path=None,
                    image_count=len(images)
                )
                
                subset_session.commit()
            
            print(f"Subset database created: {subset_db_path}")
            return subset_db_path
            
        except Exception as e:
            print(f"Error creating subset database: {e}")
            return None


class ExportPreview:
    """Handles export preview generation and analysis."""
    
    def __init__(self, export_manager: ExportManager):
        self.export_manager = export_manager
    
    def analyze_conflicts(self, preview_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze potential conflicts in export operation.
        
        Args:
            preview_data: Preview data from export_manager.preview_export()
            
        Returns:
            Dictionary with conflict analysis
        """
        conflicts = {
            'filename_conflicts': [],
            'directory_collisions': [],
            'overwrite_warnings': []
        }
        
        try:
            target_mapping = preview_data.get('target_mapping', {})
            
            # Group by target path to find conflicts
            path_groups = defaultdict(list)
            for source_path, target_path in target_mapping.items():
                path_groups[target_path].append(source_path)
            
            # Find filename conflicts
            for target_path, source_paths in path_groups.items():
                if len(source_paths) > 1:
                    conflicts['filename_conflicts'].append({
                        'target_path': target_path,
                        'source_paths': source_paths,
                        'resolution': 'Files will be renamed with numeric suffixes'
                    })
            
            # Check for existing files that would be overwritten
            for target_path in target_mapping.values():
                if os.path.exists(target_path):
                    conflicts['overwrite_warnings'].append({
                        'path': target_path,
                        'resolution': 'Existing file will be renamed'
                    })
            
            return conflicts
            
        except Exception as e:
            print(f"Error analyzing conflicts: {e}")
            return conflicts
    
    def generate_summary_report(self, preview_data: Dict[str, Any]) -> str:
        """Generate a human-readable summary of the export preview."""
        try:
            total = preview_data['total_images']
            directories = preview_data['directories']
            conflicts = preview_data['conflicts']
            errors = preview_data['errors']
            size_mb = preview_data.get('estimated_size_mb', 0)
            
            report = []
            report.append(f"Export Preview - {total} images match query")
            report.append(f"Estimated size: {size_mb:.1f} MB")
            report.append("")
            
            if directories:
                report.append("Directory breakdown:")
                for directory, count in sorted(directories.items()):
                    report.append(f"  {directory} - {count} images")
                report.append("")
            
            if conflicts:
                report.append("Conflicts found:")
                for conflict in conflicts:
                    report.append(f"  - {conflict['filename']}: {conflict.get('resolution', 'Will be resolved automatically')}")
                report.append("")
            
            if errors:
                report.append("Errors:")
                for error in errors:
                    report.append(f"  - {error['image']}: {error['error']}")
                report.append("")
            
            return "\n".join(report)
            
        except Exception as e:
            return f"Error generating summary: {e}"


def validate_export_template(template: str) -> Tuple[bool, str]:
    """
    Validate export structure template.
    
    Args:
        template: Template string like "{year}/{event_tag}"
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Check for valid placeholders
        valid_placeholders = [
            'year', 'month', 'day', 'date',
            'event_tag', 'scene_tag', 'people_tag',
            'photographer'
        ]
        
        # Find all placeholders in template
        placeholders = re.findall(r'{(\w+)}', template)
        
        # Check if all placeholders are valid
        invalid = [p for p in placeholders if p not in valid_placeholders]
        if invalid:
            return False, f"Invalid placeholders: {', '.join(invalid)}"
        
        # Check for path traversal attempts
        if '..' in template or template.startswith('/'):
            return False, "Template cannot contain '..' or start with '/'"
        
        return True, ""
        
    except Exception as e:
        return False, f"Error validating template: {e}"


def get_export_size_estimate(images: List[Image]) -> Dict[str, Any]:
    """
    Calculate size estimates for export operation.
    
    Args:
        images: List of images to export
        
    Returns:
        Dictionary with size information
    """
    try:
        total_bytes = sum(img.file_size or 0 for img in images)
        
        return {
            'total_bytes': total_bytes,
            'total_mb': total_bytes / (1024 * 1024),
            'total_gb': total_bytes / (1024 * 1024 * 1024),
            'file_count': len(images),
            'average_file_size_mb': (total_bytes / len(images)) / (1024 * 1024) if images else 0
        }
        
    except Exception as e:
        print(f"Error calculating export size: {e}")
        return {'total_bytes': 0, 'total_mb': 0, 'total_gb': 0, 'file_count': 0}