"""
Default configuration values for the photo manager application.
"""

DEFAULT_CONFIG = {
    'ui': {
        'start_fullscreen': True,
        'default_zoom': 'fit_to_canvas',  # no_zoom, fit_to_canvas, fill_canvas
        'max_zoom_percent': 200,          # Maximum zoom percentage (200 = 200% = 2x)
        'undo_queue_size': 1000,
        'preload_next_images': 3,         # Pre-load next n images
        'retain_previous_images': 2,      # Keep previous n in cache
        'default_window_width': 1200,
        'default_window_height': 800,
        'info_display_level': 2,          # 1-3, amount of info shown
        'theme': 'dark'                   # Qt theme preference
    },
    
    'hotkeys': {
        'custom': {
            # Default hotkeys for common tags
            'b': 'event_tags/birthday',
            'v': 'event_tags/vacation',
            'g': 'people_tags/child1',
            'shift_g': 'people_tags/child2',
            'h': 'scene_tags/hiking',
            'o': 'scene_tags/outdoor',
            'i': 'scene_tags/indoor'
        }
    },
    
    'slideshow': {
        'duration': 5.0,                  # Seconds per image
        'transition': 'fade',             # fade, wipe, replace
        'transition_duration': 1.0,       # Transition duration in seconds
        'random_order': False,
        'show_info': False,
        'loop': True,                     # Loop back to beginning
        'include_subfolders': True,
        'gif_animation_speed': 1.0        # GIF animation speed multiplier (1.0 = normal, 0.5 = half speed, 2.0 = double speed)
    },
    
    'database': {
        'type': 'sqlite',                 # sqlite, postgresql, mysql
        'database_name': '.photo_manager.db',
        'backup_on_startup': True,
        'auto_cleanup_missing': False     # Automatically remove missing files
    },
    
    'duplicate_detection': {
        'similarity_threshold': 5,        # Hamming distance for perceptual hash
        'auto_detect': True,             # Detect duplicates when adding files
        'hash_algorithms': ['phash', 'dhash'],  # Algorithms to use
        'background_processing': True     # Calculate hashes in background
    },
    
    'file_scanning': {
        'include_subdirectories': True,
        'supported_formats': [
            'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'tif', 
            'webp', 'ico', 'psd', 'svg'
        ],
        'video_formats_to_skip': [
            'mp4', 'avi', 'wmv', 'mov', 'flv', 'mpg', 'mpeg', 
            'mpe', 'mpv', 'ogg', 'm4p', 'm4v', 'qt', 'swf'
        ],
        'ignore_hidden_files': True,
        'ignore_patterns': [
            'Thumbs.db',    # Windows thumbnails
            '.DS_Store'     # macOS metadata
        ],
        'max_file_size_mb': 500          # Skip files larger than this
    },
    
    'performance': {
        'image_cache_size_mb': 512,      # Memory limit for image cache
        'thumbnail_size': [256, 256],    # Thumbnail dimensions for cache
        'background_threads': 2,         # Number of background processing threads
        'preload_timeout_seconds': 30    # Timeout for preloading operations
    },
    
    'export': {
        'default_structure_template': '{year}/{event_tag}',
        'handle_no_tags': 'other_folder', # Create 'Other' folder for untagged images
        'collision_resolution': 'combine_tags', # How to handle multiple matching tags
        'preserve_timestamps': True,
        'create_subset_database': False   # Default for database export
    },
    
    'logging': {
        'level': 'INFO',                 # DEBUG, INFO, WARNING, ERROR
        'log_to_file': False,
        'log_file': 'photo_manager.log'
    }
}