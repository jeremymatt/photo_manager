"""
Common utility functions and helpers for the photo manager.
"""

import os
import sys
import time
import hashlib
from datetime import datetime, timedelta
from typing import Any, Optional, List, Dict, Tuple
from pathlib import Path


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string (e.g., "1.5 MB")
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    i = 0
    
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    
    return f"{size:.1f} {size_names[i]}"


def format_duration(seconds: float) -> str:
    """
    Format duration in human-readable format.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)
        return f"{minutes}m {remaining_seconds}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def safe_mkdir(directory: str) -> bool:
    """
    Safely create directory with error handling.
    
    Args:
        directory: Directory path to create
        
    Returns:
        True if successful or already exists
    """
    try:
        os.makedirs(directory, exist_ok=True)
        return True
    except Exception as e:
        print(f"Error creating directory {directory}: {e}")
        return False


def safe_file_operation(operation: callable, *args, **kwargs) -> Tuple[bool, Optional[str]]:
    """
    Safely execute file operation with error handling.
    
    Args:
        operation: Function to execute
        *args: Arguments for the function
        **kwargs: Keyword arguments for the function
        
    Returns:
        Tuple of (success, error_message)
    """
    try:
        operation(*args, **kwargs)
        return True, None
    except Exception as e:
        return False, str(e)


def get_relative_path(file_path: str, base_path: str) -> str:
    """
    Get relative path from base path, handling cross-platform issues.
    
    Args:
        file_path: Full file path
        base_path: Base directory path
        
    Returns:
        Relative path string
    """
    try:
        return os.path.relpath(file_path, base_path)
    except ValueError:
        # Paths on different drives (Windows)
        return file_path


def normalize_path(path: str) -> str:
    """
    Normalize path for cross-platform compatibility.
    
    Args:
        path: File or directory path
        
    Returns:
        Normalized path
    """
    return os.path.normpath(os.path.abspath(path))


def is_image_file(file_path: str) -> bool:
    """
    Check if file is likely an image based on extension.
    
    Args:
        file_path: Path to file
        
    Returns:
        True if likely an image file
    """
    image_extensions = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
        '.webp', '.ico', '.psd', '.svg'
    }
    
    extension = Path(file_path).suffix.lower()
    return extension in image_extensions


def calculate_file_hash(file_path: str, algorithm: str = 'md5') -> Optional[str]:
    """
    Calculate file hash for integrity checking.
    
    Args:
        file_path: Path to file
        algorithm: Hash algorithm ('md5', 'sha256')
        
    Returns:
        Hash string or None if failed
    """
    try:
        hash_obj = hashlib.new(algorithm)
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        
        return hash_obj.hexdigest()
        
    except Exception as e:
        print(f"Error calculating hash for {file_path}: {e}")
        return None


def ensure_unique_filename(directory: str, filename: str) -> str:
    """
    Ensure filename is unique in directory by adding counter if needed.
    
    Args:
        directory: Target directory
        filename: Desired filename
        
    Returns:
        Unique filename
    """
    base_name, extension = os.path.splitext(filename)
    counter = 1
    unique_filename = filename
    
    while os.path.exists(os.path.join(directory, unique_filename)):
        unique_filename = f"{base_name}_{counter}{extension}"
        counter += 1
    
    return unique_filename


def batch_rename_files(file_paths: List[str], name_pattern: str) -> List[Tuple[str, str]]:
    """
    Generate new names for batch file renaming.
    
    Args:
        file_paths: List of file paths to rename
        name_pattern: Pattern like "vacation_{counter:03d}"
        
    Returns:
        List of (old_path, new_path) tuples
    """
    rename_list = []
    
    try:
        for i, file_path in enumerate(file_paths, 1):
            directory = os.path.dirname(file_path)
            extension = Path(file_path).suffix
            
            # Replace pattern variables
            new_name = name_pattern.format(
                counter=i,
                date=datetime.now().strftime("%Y%m%d"),
                timestamp=datetime.now().strftime("%Y%m%d_%H%M%S")
            )
            
            new_filename = f"{new_name}{extension}"
            new_path = os.path.join(directory, new_filename)
            
            # Ensure uniqueness
            new_filename = ensure_unique_filename(directory, new_filename)
            new_path = os.path.join(directory, new_filename)
            
            rename_list.append((file_path, new_path))
        
        return rename_list
        
    except Exception as e:
        print(f"Error generating rename list: {e}")
        return []


def validate_file_permissions(file_path: str, operation: str) -> Tuple[bool, str]:
    """
    Validate file permissions for specified operation.
    
    Args:
        file_path: Path to file or directory
        operation: Operation type ('read', 'write', 'delete')
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        if not os.path.exists(file_path):
            return False, "File does not exist"
        
        if operation == 'read':
            if not os.access(file_path, os.R_OK):
                return False, "No read permission"
        elif operation == 'write':
            if os.path.isfile(file_path):
                if not os.access(file_path, os.W_OK):
                    return False, "No write permission"
            else:
                # Check parent directory for write permission
                parent = os.path.dirname(file_path)
                if not os.access(parent, os.W_OK):
                    return False, "No write permission in parent directory"
        elif operation == 'delete':
            if not os.access(os.path.dirname(file_path), os.W_OK):
                return False, "No delete permission"
        
        return True, ""
        
    except Exception as e:
        return False, str(e)


def clean_filename(filename: str) -> str:
    """
    Clean filename by removing invalid characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Cleaned filename safe for all platforms
    """
    # Invalid characters for Windows (most restrictive)
    invalid_chars = '<>:"|?*'
    
    cleaned = filename
    for char in invalid_chars:
        cleaned = cleaned.replace(char, '_')
    
    # Remove leading/trailing spaces and dots
    cleaned = cleaned.strip(' .')
    
    # Ensure not empty
    if not cleaned:
        cleaned = "unnamed_file"
    
    return cleaned


def prompt_yes_no(message: str, default: bool = False) -> bool:
    """
    Prompt user for yes/no confirmation.
    
    Args:
        message: Message to display
        default: Default value if user just presses Enter
        
    Returns:
        True for yes, False for no
    """
    default_text = "(Y/n)" if default else "(y/N)"
    
    try:
        response = input(f"{message} {default_text}: ").strip().lower()
        
        if not response:
            return default
        
        return response in ['y', 'yes', 'true', '1']
        
    except KeyboardInterrupt:
        return False


def estimate_processing_time(num_items: int, items_per_second: float) -> str:
    """
    Estimate processing time for batch operations.
    
    Args:
        num_items: Number of items to process
        items_per_second: Processing rate
        
    Returns:
        Formatted time estimate
    """
    if items_per_second <= 0:
        return "unknown"
    
    total_seconds = num_items / items_per_second
    return format_duration(total_seconds)


def get_system_info() -> Dict[str, Any]:
    """
    Get basic system information for debugging.
    
    Returns:
        Dictionary with system information
    """
    info = {
        'platform': sys.platform,
        'python_version': sys.version,
        'working_directory': os.getcwd(),
        'available_memory_mb': 'unknown'  # Would need psutil for real memory info
    }
    
    try:
        # Try to get memory info (optional)
        import psutil
        memory = psutil.virtual_memory()
        info['available_memory_mb'] = memory.available // (1024 * 1024)
    except ImportError:
        pass
    
    return info


class ProgressTracker:
    """Tracks progress of long-running operations."""
    
    def __init__(self, total_items: int, description: str = "Processing"):
        """
        Initialize progress tracker.
        
        Args:
            total_items: Total number of items to process
            description: Description of the operation
        """
        self.total_items = total_items
        self.description = description
        self.processed_items = 0
        self.start_time = time.time()
        self.last_update = 0
    
    def update(self, increment: int = 1, current_item: str = "") -> bool:
        """
        Update progress.
        
        Args:
            increment: Number of items processed
            current_item: Description of current item
            
        Returns:
            True if should display update (rate limited)
        """
        self.processed_items += increment
        current_time = time.time()
        
        # Rate limit updates (max once per second)
        if current_time - self.last_update < 1.0 and self.processed_items < self.total_items:
            return False
        
        self.last_update = current_time
        
        # Calculate progress
        progress_pct = (self.processed_items / self.total_items) * 100
        elapsed_time = current_time - self.start_time
        
        if self.processed_items > 0 and elapsed_time > 0:
            items_per_second = self.processed_items / elapsed_time
            remaining_items = self.total_items - self.processed_items
            eta_seconds = remaining_items / items_per_second
            eta_str = format_duration(eta_seconds)
        else:
            eta_str = "calculating..."
        
        status = f"{self.description}: {self.processed_items}/{self.total_items} ({progress_pct:.1f}%) - ETA: {eta_str}"
        
        if current_item:
            status += f" - {current_item}"
        
        print(f"\r{status}", end="", flush=True)
        
        if self.processed_items >= self.total_items:
            print()  # New line when complete
        
        return True
    
    def complete(self, message: str = "Complete"):
        """Mark operation as complete."""
        elapsed = time.time() - self.start_time
        print(f"\n{message} - {self.processed_items} items in {format_duration(elapsed)}")


def backup_file(file_path: str, backup_suffix: str = None) -> Optional[str]:
    """
    Create a backup copy of a file.
    
    Args:
        file_path: Path to file to backup
        backup_suffix: Optional suffix for backup file
        
    Returns:
        Path to backup file or None if failed
    """
    try:
        if not os.path.exists(file_path):
            return None
        
        if not backup_suffix:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_suffix = f"backup_{timestamp}"
        
        backup_path = f"{file_path}.{backup_suffix}"
        
        import shutil
        shutil.copy2(file_path, backup_path)
        
        return backup_path
        
    except Exception as e:
        print(f"Error creating backup of {file_path}: {e}")
        return None