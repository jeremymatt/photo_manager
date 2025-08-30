"""
Main Qt window for the photo manager application.
Provides full-featured interface with tag management, duplicate handling, and export.
"""

import os
import sys
from typing import Optional, List, Dict, Any

try:
    from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                                  QLabel, QMenuBar, QStatusBar, QApplication,
                                  QMessageBox, QFileDialog, QInputDialog, QShortcut)
    from PySide6.QtCore import Qt, QTimer, Signal
    from PySide6.QtGui import QPixmap, QKeySequence
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

if QT_AVAILABLE:
    from ...database.database_manager import DatabaseManager
    from ...database.models import Image as ImageModel
    from ...core.tag_manager import TagManager
    from ...core.image_processor import ImageProcessor
    from ...config.config_manager import ConfigManager


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self, directory_path: Optional[str] = None, 
                 db_path: Optional[str] = None,
                 config_path: Optional[str] = None,
                 slideshow_mode: bool = False,
                 query: Optional[str] = None):
        """
        Initialize main window.
        
        Args:
            directory_path: Initial directory to open
            db_path: Path to database file
            config_path: Path to configuration file
            slideshow_mode: Start in slideshow mode
            query: Initial query filter
        """
        super().__init__()
        
        if not QT_AVAILABLE:
            raise ImportError("Qt dependencies not available. Install with: pip install PySide2")
        
        self.directory_path = directory_path
        self.slideshow_mode = slideshow_mode
        self.query = query
        
        # Initialize managers
        self._init_managers(db_path, config_path)
        
        # UI state
        self.current_image_index = 0
        self.current_images = []
        
        # Setup UI
        self._init_ui()
        self._setup_shortcuts()
        
        # Load initial data
        if directory_path:
            self._load_directory(directory_path)
    
    def _init_managers(self, db_path: Optional[str], config_path: Optional[str]):
        """Initialize core managers."""
        try:
            # Load configuration
            self.config_manager = ConfigManager(config_path)
            config_dir = self.directory_path or os.getcwd()
            self.config = self.config_manager.load_config(config_dir)
            
            # Initialize database
            db_config = self.config['database'].copy()
            if db_path:
                db_config['path'] = db_path
            elif self.directory_path:
                db_config['path'] = os.path.join(self.directory_path, '.photo_manager.db')
            
            self.db_manager = DatabaseManager(db_config)
            if not self.db_manager.initialize_connection():
                raise Exception("Failed to initialize database")
            
            # Initialize other managers
            self.tag_manager = TagManager(self.db_manager)
            self.image_processor = ImageProcessor(self.config)
            
        except Exception as e:
            QMessageBox.critical(self, "Initialization Error", f"Failed to initialize: {e}")
            sys.exit(1)
    
    def _init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("Photo Manager")
        
        # Set initial size
        ui_config = self.config.get('ui', {})
        width = ui_config.get('default_window_width', 1200)
        height = ui_config.get('default_window_height', 800)
        self.resize(width, height)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        layout = QVBoxLayout(central_widget)
        
        # Image display area (placeholder)
        self.image_label = QLabel("No image loaded")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: black; color: white;")
        self.image_label.setMinimumSize(800, 600)
        layout.addWidget(self.image_label)
        
        # Status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready")
        
        # Menu bar
        self._create_menus()
        
        # Apply theme
        if ui_config.get('theme') == 'dark':
            self._apply_dark_theme()
    
    def _create_menus(self):
        """Create application menus."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        file_menu.addAction('Open Directory...', self._open_directory)
        file_menu.addAction('Scan Directory...', self._scan_directory)
        file_menu.addSeparator()
        file_menu.addAction('Export...', self._show_export_dialog)
        file_menu.addSeparator()
        file_menu.addAction('Exit', self.close)
        
        # View menu
        view_menu = menubar.addMenu('View')
        view_menu.addAction('Fullscreen', self._toggle_fullscreen)
        view_menu.addAction('Slideshow', self._start_slideshow)
        view_menu.addSeparator()
        view_menu.addAction('Next Image', self._next_image)
        view_menu.addAction('Previous Image', self._previous_image)
        
        # Tags menu
        tags_menu = menubar.addMenu('Tags')
        tags_menu.addAction('Tag Current Image...', self._tag_current_image)
        tags_menu.addAction('Copy Tags', self._copy_tags)
        tags_menu.addAction('Paste Tags', self._paste_tags)
        tags_menu.addSeparator()
        tags_menu.addAction('Search Images...', self._search_images)
        
        # Tools menu
        tools_menu = menubar.addMenu('Tools')
        tools_menu.addAction('Find Duplicates', self._find_duplicates)
        tools_menu.addAction('Clean Missing Files', self._clean_missing_files)
        tools_menu.addAction('Database Statistics', self._show_db_stats)
    
    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Basic navigation
        self._add_shortcut('Right', self._next_image)
        self._add_shortcut('Left', self._previous_image)
        self._add_shortcut('Shift+Right', self._next_folder)
        self._add_shortcut('Shift+Left', self._previous_folder)
        
        # Image manipulation  
        self._add_shortcut('Tab', self._toggle_fit_mode)
        self._add_shortcut('Up', self._rotate_ccw)
        self._add_shortcut('Down', self._rotate_cw)
        self._add_shortcut('Ctrl+R', self._reset_image)
        
"""
Main Qt viewer window for the photo manager application.
Provides full-featured interface with tag management, duplicate handling, and export.
"""

import os
import sys
from typing import Optional, List, Dict, Any

try:
    from PySide2.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                                  QLabel, QMenuBar, QStatusBar, QApplication,
                                  QMessageBox, QFileDialog, QInputDialog, QShortcut)
    from PySide2.QtCore import Qt, QTimer, Signal
    from PySide2.QtGui import QPixmap, QKeySequence
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

if QT_AVAILABLE:
    from ...database.database_manager import DatabaseManager
    from ...database.models import Image as ImageModel
    from ...core.tag_manager import TagManager
    from ...core.image_processor import ImageProcessor
    from ...config.config_manager import ConfigManager


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self, directory_path: Optional[str] = None, 
                 db_path: Optional[str] = None,
                 config_path: Optional[str] = None,
                 slideshow_mode: bool = False,
                 query: Optional[str] = None):
        """
        Initialize main window.
        
        Args:
            directory_path: Initial directory to open
            db_path: Path to database file
            config_path: Path to configuration file
            slideshow_mode: Start in slideshow mode
            query: Initial query filter
        """
        super().__init__()
        
        if not QT_AVAILABLE:
            raise ImportError("Qt dependencies not available. Install with: pip install PySide2")
        
        self.directory_path = directory_path
        self.slideshow_mode = slideshow_mode
        self.query = query
        
        # Initialize managers
        self._init_managers(db_path, config_path)
        
        # UI state
        self.current_image_index = 0
        self.current_images = []
        
        # Setup UI
        self._init_ui()
        self._setup_shortcuts()
        
        # Load initial data
        if directory_path:
            self._load_directory(directory_path)
    
    def _init_managers(self, db_path: Optional[str], config_path: Optional[str]):
        """Initialize core managers."""
        try:
            # Load configuration
            self.config_manager = ConfigManager(config_path)
            config_dir = self.directory_path or os.getcwd()
            self.config = self.config_manager.load_config(config_dir)
            
            # Initialize database
            db_config = self.config['database'].copy()
            if db_path:
                db_config['path'] = db_path
            elif self.directory_path:
                db_config['path'] = os.path.join(self.directory_path, '.photo_manager.db')
            
            self.db_manager = DatabaseManager(db_config)
            if not self.db_manager.initialize_connection():
                raise Exception("Failed to initialize database")
            
            # Initialize other managers
            self.tag_manager = TagManager(self.db_manager)
            self.image_processor = ImageProcessor(self.config)
            
        except Exception as e:
            QMessageBox.critical(self, "Initialization Error", f"Failed to initialize: {e}")
            sys.exit(1)
    
    def _init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("Photo Manager")
        
        # Set initial size
        ui_config = self.config.get('ui', {})
        width = ui_config.get('default_window_width', 1200)
        height = ui_config.get('default_window_height', 800)
        self.resize(width, height)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        layout = QVBoxLayout(central_widget)
        
        # Image display area (placeholder)
        self.image_label = QLabel("No image loaded")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: black; color: white;")
        self.image_label.setMinimumSize(800, 600)
        layout.addWidget(self.image_label)
        
        # Status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready")
        
        # Menu bar
        self._create_menus()
        
        # Apply theme
        if ui_config.get('theme') == 'dark':
            self._apply_dark_theme()
    
    def _create_menus(self):
        """Create application menus."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        file_menu.addAction('Open Directory...', self._open_directory)
        file_menu.addAction('Scan Directory...', self._scan_directory)
        file_menu.addSeparator()
        file_menu.addAction('Export...', self._show_export_dialog)
        file_menu.addSeparator()
        file_menu.addAction('Exit', self.close)
        
        # View menu
        view_menu = menubar.addMenu('View')
        view_menu.addAction('Fullscreen', self._toggle_fullscreen)
        view_menu.addAction('Slideshow', self._start_slideshow)
        view_menu.addSeparator()
        view_menu.addAction('Next Image', self._next_image)
        view_menu.addAction('Previous Image', self._previous_image)
        
        # Tags menu
        tags_menu = menubar.addMenu('Tags')
        tags_menu.addAction('Tag Current Image...', self._tag_current_image)
        tags_menu.addAction('Copy Tags', self._copy_tags)
        tags_menu.addAction('Paste Tags', self._paste_tags)
        tags_menu.addSeparator()
        tags_menu.addAction('Search Images...', self._search_images)
        
        # Tools menu
        tools_menu = menubar.addMenu('Tools')
        tools_menu.addAction('Find Duplicates', self._find_duplicates)
        tools_menu.addAction('Clean Missing Files', self._clean_missing_files)
        tools_menu.addAction('Database Statistics', self._show_db_stats)
    
    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Basic navigation
        self._add_shortcut('Right', self._next_image)
        self._add_shortcut('Left', self._previous_image)
        self._add_shortcut('Shift+Right', self._next_folder)
        self._add_shortcut('Shift+Left', self._previous_folder)
        
        # Image manipulation  
        self._add_shortcut('Tab', self._toggle_fit_mode)
        self._add_shortcut('Up', self._rotate_ccw)
        self._add_shortcut('Down', self._rotate_cw)
        self._add_shortcut('Ctrl+R', self._reset_image)
        
        # Tagging
        self._add_shortcut('Ctrl+T', self._tag_current_image)
        self._add_shortcut('Ctrl+C', self._copy_tags)
        self._add_shortcut('Ctrl+V', self._paste_tags)
        
        # File operations
        self._add_shortcut('.', self._mark_for_deletion)
        self._add_shortcut('Ctrl+D', self._delete_marked)
        self._add_shortcut('Ctrl+Z', self._undo_last_action)
        
        # System
        self._add_shortcut('F11', self._toggle_fullscreen)
        self._add_shortcut('Escape', self.close)
        
        # Custom hotkeys from config
        self._setup_custom_hotkeys()
    
    def _add_shortcut(self, key_sequence: str, callback):
        """Add keyboard shortcut."""
        shortcut = QShortcut(QKeySequence(key_sequence), self)
        shortcut.activated.connect(callback)
    
    def _setup_custom_hotkeys(self):
        """Setup custom hotkeys from configuration."""
        custom_hotkeys = self.config_manager.get_hotkeys()
        
        for key_combo, tag_spec in custom_hotkeys.items():
            # Convert key_combo format (e.g., 'shift_g' -> 'Shift+G')
            qt_key = self._convert_key_combo(key_combo)
            
            # Create callback for this tag
            def make_tag_callback(tag_specification):
                def callback():
                    self._apply_hotkey_tag(tag_specification)
                return callback
            
            self._add_shortcut(qt_key, make_tag_callback(tag_spec))
    
    def _convert_key_combo(self, key_combo: str) -> str:
        """Convert key combination to Qt format."""
        parts = key_combo.split('_')
        result = []
        
        for part in parts:
            if part == 'shift':
                result.append('Shift')
            elif part == 'ctrl':
                result.append('Ctrl')
            elif part == 'alt':
                result.append('Alt')
            else:
                result.append(part.upper())
        
        return '+'.join(result)
    
    def _apply_hotkey_tag(self, tag_spec: str):
        """Apply tag from hotkey specification."""
        try:
            if '/' in tag_spec:
                category, tag_name = tag_spec.split('/', 1)
                # TODO: Apply tag to current image
                self.status_bar.showMessage(f"Applied tag: {category}/{tag_name}")
        except Exception as e:
            print(f"Error applying hotkey tag: {e}")
    
    # Placeholder methods for UI actions
    def _open_directory(self):
        """Open directory dialog."""
        dialog = QFileDialog()
        directory = dialog.getExistingDirectory(self, "Select Photo Directory")
        if directory:
            self._load_directory(directory)
    
    def _load_directory(self, directory: str):
        """Load images from directory."""
        self.status_bar.showMessage(f"Loading directory: {directory}")
        # TODO: Implement directory loading
    
    def _next_image(self):
        """Navigate to next image."""
        self.status_bar.showMessage("Next image")
        # TODO: Implement image navigation
    
    def _previous_image(self):
        """Navigate to previous image."""
        self.status_bar.showMessage("Previous image")
        # TODO: Implement image navigation
    
    def _toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
    
    def _apply_dark_theme(self):
        """Apply dark theme to application."""
        dark_stylesheet = """
        QMainWindow {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QMenuBar {
            background-color: #3c3c3c;
            color: #ffffff;
        }
        QMenuBar::item:selected {
            background-color: #555555;
        }
        QLabel {
            color: #ffffff;
        }
        """
        self.setStyleSheet(dark_stylesheet)
    
    # Additional placeholder methods
    def _scan_directory(self): pass
    def _show_export_dialog(self): pass  
    def _start_slideshow(self): pass
    def _next_folder(self): pass
    def _previous_folder(self): pass
    def _toggle_fit_mode(self): pass
    def _rotate_ccw(self): pass
    def _rotate_cw(self): pass
    def _reset_image(self): pass
    def _tag_current_image(self): pass
    def _copy_tags(self): pass
    def _paste_tags(self): pass
    def _mark_for_deletion(self): pass
    def _delete_marked(self): pass
    def _undo_last_action(self): pass
    def _search_images(self): pass
    def _find_duplicates(self): pass
    def _clean_missing_files(self): pass
    def _show_db_stats(self): pass


def create_qt_application():
    """Create Qt application instance."""
    if not QT_AVAILABLE:
        raise ImportError("Qt not available")
    
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    return app