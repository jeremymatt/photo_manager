"""
Photo Manager - Fast Image Viewer & File Manager

A lightweight, keyboard-driven image viewer and file manager with database-backed
tagging, duplicate detection, and slideshow capabilities.
"""

__version__ = "0.1.0"
__author__ = "Photo Manager Project"

# Import key classes for easy access
from .database.database_manager import DatabaseManager
from .database.models import Image, Tag, ImageTag
from .config.config_manager import ConfigManager
from .core.tag_manager import TagManager
from .core.image_processor import ImageProcessor

__all__ = [
    'DatabaseManager',
    'ConfigManager', 
    'TagManager',
    'ImageProcessor',
    'Image',
    'Tag',
    'ImageTag'
]