"""
Main Qt window for the photo manager application.
Coordinates between specialized controllers and provides the main UI layout.
"""

import os
import sys
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QStatusBar, QApplication, QMessageBox, QFileDialog,
    QSplitter, QListWidget, QTextEdit, QPushButton, QProgressBar, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QAction

# Import with fallbacks for development
try:
    from ...database.database_manager import DatabaseManager
    from ...database.models import Image as ImageModel
    from ...core.tag_manager import TagManager
    from ...core.image_processor import ImageProcessor
    from ...config.config_manager import ConfigManager
except ImportError as e:
    print(f"Warning: Could not import some modules: {e}")
    # Create fallback classes
    DatabaseManager = None
    ImageModel = None
    TagManager = None
    ImageProcessor = None
    ConfigManager = None

from .image_display import ImageDisplayWidget
from .keyboard_handler import KeyboardHandler, ShortcutHelpDialog
from .navigation_controller import NavigationController
from .slideshow import start_slideshow
from .dialogs import (
    show_tag_management_dialog, show_export_dialog, 
    show_query_builder, show_database_maintenance
)


class MainWindow(QMainWindow):
    """
    Main application window that coordinates between specialized controllers.
    Provides UI layout and delegates functionality to appropriate modules.
    """
    
    def __init__(self, directory_path: Optional[str] = None, 
                 db_path: Optional[str] = None,
                 config_path: Optional[str] = None,
                 slideshow_mode: bool = False,
                 query: Optional[str] = None):
        super().__init__()
        
        self.directory_path = directory_path
        self.slideshow_mode = slideshow_mode
        self.query = query
        
        # Core managers
        self.config_manager = None
        self.db_manager = None
        self.tag_manager = None
        self.image_processor = None
        
        # UI controllers
        self.image_display = None
        self.keyboard_handler = None
        self.navigation_controller = None
        
        # Initialize everything
        self._init_managers(db_path, config_path)
        self._init_controllers()
        self._init_ui()
        self._connect_signals()
        
        # Load initial data
        if directory_path:
            print(f"Loading directory: {directory_path}")
            success = self.navigation_controller.load_directory(directory_path)
            if not success:
                self._show_error("Load Error", f"Failed to load directory: {directory_path}")
            elif not self.navigation_controller.current_images:
                self._show_info("No Images", f"No images found in: {directory_path}")
        
        # Start slideshow if requested
        if slideshow_mode and self.navigation_controller.current_images:
            self._start_slideshow()
    
    def _init_managers(self, db_path: Optional[str], config_path: Optional[str]):
        """Initialize core managers."""
        print(f"Initializing managers with directory: {self.directory_path}")
        print(f"Config path: {config_path}")
        print(f"DB path: {db_path}")
        
        try:
            # Configuration manager
            try:
                if ConfigManager:
                    print("Using ConfigManager")
                    self.config_manager = ConfigManager(config_path)
                    config_dir = self.directory_path or os.getcwd()
                    print(f"Loading config from directory: {config_dir}")
                    
                    # Check if config.yaml exists in the target directory
                    config_file_path = os.path.join(config_dir, 'config.yaml')
                    if os.path.exists(config_file_path):
                        print(f"Found config file: {config_file_path}")
                    else:
                        print(f"No config file found at: {config_file_path}")
                    
                    self.config = self.config_manager.load_config(config_dir)
                    print(f"Loaded config keys: {list(self.config.keys())}")
                else:
                    print("ConfigManager not available, using defaults")
                    self.config = self._get_default_config()
            except Exception as e:
                print(f"Config manager initialization failed: {e}")
                import traceback
                traceback.print_exc()
                self.config = self._get_default_config()
            
            # Database manager
            try:
                if DatabaseManager:
                    db_config = self.config.get('database', {})
                    
                    print('\n=== Database Config Debug ===')
                    print(f'Raw db_config: {db_config}')
                    for key in db_config.keys():
                        print(f'  {key}: {db_config[key]}')
                    
                    if db_path:
                        print(f"Using explicit db_path: {db_path}")
                        db_config['path'] = db_path
                    elif self.directory_path:
                        # Use database_name from config if available, otherwise default
                        db_name = db_config.get('database_name', '.photo_manager.db')
                        full_db_path = os.path.join(self.directory_path, db_name)
                        print(f"Using directory-based path: {full_db_path}")
                        db_config['path'] = full_db_path
                    else:
                        print("No directory specified, using default database path")
                        db_config['path'] = db_config.get('database_name', '.photo_manager.db')
                    
                    print(f"Final database path: {db_config['path']}")
                    print(f"Database file exists: {os.path.exists(db_config['path'])}")
                    print('==============================\n')
                    
                    self.db_manager = DatabaseManager(db_config)
                    
                    if self.db_manager.initialize_connection():
                        print("Database connection established successfully")
                    else:
                        print("Database connection failed")
                        self.db_manager = None
                else:
                    print("DatabaseManager class not available")
                    self.db_manager = None
            except Exception as e:
                print(f"Database manager initialization failed: {e}")
                import traceback
                traceback.print_exc()
                self.db_manager = None
            
            # Other managers
            try:
                if TagManager and self.db_manager:
                    self.tag_manager = TagManager(self.db_manager)
                    print("Tag manager initialized")
                else:
                    print("Tag manager not initialized (no database or TagManager class)")
                    self.tag_manager = None
            except Exception as e:
                print(f"Tag manager initialization failed: {e}")
                self.tag_manager = None
            
            try:
                if ImageProcessor:
                    self.image_processor = ImageProcessor(self.config)
                    print("Image processor initialized")
                else:
                    print("ImageProcessor class not available")
            except Exception as e:
                print(f"Image processor initialization failed: {e}")
                self.image_processor = None
                
        except Exception as e:
            print(f"Manager initialization error: {e}")
            import traceback
            traceback.print_exc()
            self.config = self._get_default_config()
    
    def _init_controllers(self):
        """Initialize UI controllers."""
        self.image_display = ImageDisplayWidget()
        self.navigation_controller = NavigationController(
            self.db_manager, self.tag_manager, self
        )
    
    def _get_default_config(self):
        """Get default configuration."""
        return {
            'ui': {
                'default_window_width': 1200,
                'default_window_height': 800,
                'theme': 'light',
                'start_fullscreen': False
            },
            'hotkeys': {'custom': {}},
            'slideshow': {
                'duration': 5.0,
                'transition': 'fade',
                'random_order': False
            },
            'database': {
                'type': 'sqlite',
                'database_name': '.photo_manager.db'
            }
        }
    
    def _init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("Photo Manager")
        
        # Window settings
        ui_config = self.config.get('ui', {})
        width = ui_config.get('default_window_width', 1200)
        height = ui_config.get('default_window_height', 800)
        self.resize(width, height)
        
        if ui_config.get('start_fullscreen', False):
            self.showFullScreen()
        
        # Central widget with splitter
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)
        
        # Add image display
        self.splitter.addWidget(self.image_display)
        
        # Create info panel
        self._create_info_panel()
        
        # Status bar
        self.status_bar = self.statusBar()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
        self.status_bar.showMessage("Ready")
        
        # Menu bar
        self._create_menus()
        
        # Set splitter proportions
        self.splitter.setSizes([int(width * 0.8), int(width * 0.2)])
        
        # Apply theme
        if ui_config.get('theme') == 'dark':
            self._apply_dark_theme()
        
        # Initialize keyboard handler after UI is created
        self.keyboard_handler = KeyboardHandler(self, self.config)
    
    def _create_info_panel(self):
        """Create the right information panel."""
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        
        # Image info section
        info_frame = QFrame()
        info_frame.setFrameStyle(QFrame.StyledPanel)
        info_frame_layout = QVBoxLayout(info_frame)
        
        info_frame_layout.addWidget(QLabel("Image Information"))
        self.info_text = QTextEdit()
        self.info_text.setMaximumHeight(150)
        self.info_text.setReadOnly(True)
        info_frame_layout.addWidget(self.info_text)
        
        # Tags section
        tags_frame = QFrame()
        tags_frame.setFrameStyle(QFrame.StyledPanel)
        tags_layout = QVBoxLayout(tags_frame)
        
        tags_layout.addWidget(QLabel("Tags"))
        self.tags_list = QListWidget()
        self.tags_list.setMaximumHeight(200)
        tags_layout.addWidget(self.tags_list)
        
        # Tag management buttons
        tag_buttons = QHBoxLayout()
        add_tag_btn = QPushButton("Add Tag")
        add_tag_btn.clicked.connect(self._show_tag_dialog)
        remove_tag_btn = QPushButton("Remove Tag")
        remove_tag_btn.clicked.connect(self._remove_selected_tag)
        
        tag_buttons.addWidget(add_tag_btn)
        tag_buttons.addWidget(remove_tag_btn)
        tags_layout.addLayout(tag_buttons)
        
        info_layout.addWidget(info_frame)
        info_layout.addWidget(tags_frame)
        info_layout.addStretch()
        
        self.splitter.addWidget(info_widget)
    
    def _create_menus(self):
        """Create application menus."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('&File')
        file_menu.addAction('&Open Directory...', self._open_directory)
        file_menu.addAction('&Scan Directory...', self._scan_directory)
        file_menu.addSeparator()
        file_menu.addAction('&Export...', self._show_export_dialog)
        file_menu.addSeparator()
        file_menu.addAction('E&xit', self.close)
        
        # View menu
        view_menu = menubar.addMenu('&View')
        view_menu.addAction('&Fullscreen', self._toggle_fullscreen)
        view_menu.addAction('&Slideshow', self._start_slideshow)
        view_menu.addSeparator()
        view_menu.addAction('&Next Image', self._next_image)
        view_menu.addAction('&Previous Image', self._previous_image)
        view_menu.addSeparator()
        view_menu.addAction('Zoom &In', self._zoom_in)
        view_menu.addAction('Zoom &Out', self._zoom_out)
        view_menu.addAction('&Reset View', self._reset_view)
        
        # Tags menu
        tags_menu = menubar.addMenu('&Tags')
        tags_menu.addAction('&Tag Current Image...', self._show_tag_dialog)
        tags_menu.addAction('&Copy Tags', self._copy_tags)
        tags_menu.addAction('&Paste Tags', self._paste_tags)
        tags_menu.addSeparator()
        tags_menu.addAction('&Search Images...', self._search_images)
        
        # Tools menu
        tools_menu = menubar.addMenu('&Tools')
        tools_menu.addAction('Find &Duplicates', self._find_duplicates)
        tools_menu.addAction('Database &Statistics', self._show_db_stats)
        tools_menu.addSeparator()
        tools_menu.addAction('&Keyboard Shortcuts', self._show_shortcuts_help)
    
    def _connect_signals(self):
        """Connect signals between controllers."""
        # Navigation controller signals
        self.navigation_controller.image_changed.connect(self._on_image_changed)
        self.navigation_controller.navigation_state_changed.connect(self._on_navigation_state_changed)
        self.navigation_controller.files_marked_for_deletion.connect(self._on_files_marked)
        self.navigation_controller.tags_copied.connect(self._on_tags_copied)
        self.navigation_controller.tags_pasted.connect(self._on_tags_pasted)
        
        # Image display signals
        self.image_display.image_changed.connect(self._on_image_display_changed)
        self.image_display.loading_started.connect(self._on_loading_started)
        self.image_display.loading_finished.connect(self._on_loading_finished)
        
        # Keyboard handler signals
        self.keyboard_handler.navigation_action.connect(self._handle_navigation_action)
        self.keyboard_handler.image_action.connect(self._handle_image_action)
        self.keyboard_handler.tag_action.connect(self._handle_tag_action)
        self.keyboard_handler.file_action.connect(self._handle_file_action)
        self.keyboard_handler.view_action.connect(self._handle_view_action)
    
    # Signal handlers
    def _on_image_changed(self, image_model):
        """Handle image change from navigation controller."""
        print(f"Loading image in display widget: {image_model.file_path}")
        self.image_display.load_image(image_model.file_path)
        
        filename = os.path.basename(image_model.file_path)
        nav_state = self.navigation_controller.get_navigation_state()
        self.setWindowTitle(
            f"Photo Manager - {filename} ({nav_state.current_index + 1}/{nav_state.total_images})"
        )
        
        self._update_image_info(image_model)
    
    def _on_navigation_state_changed(self, nav_state):
        """Handle navigation state change."""
        if nav_state.total_images > 0:
            status_msg = f"Image {nav_state.current_index + 1} of {nav_state.total_images}"
            if nav_state.filter_query:
                status_msg += f" (filtered)"
            self.status_bar.showMessage(status_msg)
        else:
            self.status_bar.showMessage("No images")
    
    def _on_files_marked(self, marked_files: set):
        """Handle files marked for deletion."""
        if marked_files:
            self.status_bar.showMessage(f"{len(marked_files)} files marked for deletion")
    
    def _on_tags_copied(self, tags: list):
        """Handle tags copied."""
        self.status_bar.showMessage(f"Copied {len(tags)} tags")
    
    def _on_tags_pasted(self, target_image, pasted_tags: list):
        """Handle tags pasted."""
        self.status_bar.showMessage(f"Pasted {len(pasted_tags)} tags")
        self._update_tags_display()
    
    def _on_image_display_changed(self, image_path: str):
        """Handle image display widget image change."""
        if image_path.lower().endswith('.gif'):
            self.keyboard_handler.set_context_mode('gif_focus')
        else:
            self.keyboard_handler.set_context_mode('normal')
    
    def _on_loading_started(self):
        """Handle image loading start."""
        self.progress_bar.setVisible(True)
        self.status_bar.showMessage("Loading image...")
    
    def _on_loading_finished(self):
        """Handle image loading completion."""
        self.progress_bar.setVisible(False)
    
    # Keyboard action handlers
    def _handle_navigation_action(self, action_name: str, context: dict):
        """Handle navigation keyboard actions."""
        if action_name == "next_image":
            self.navigation_controller.next_image()
        elif action_name == "previous_image":
            self.navigation_controller.previous_image()
        elif action_name == "first_image":
            self.navigation_controller.first_image()
        elif action_name == "last_image":
            self.navigation_controller.last_image()
        elif action_name == "search_images":
            self._search_images()
    
    def _handle_image_action(self, action_name: str, context: dict):
        """Handle image manipulation keyboard actions."""
        if action_name == "zoom_in":
            self.image_display.zoom_in()
        elif action_name == "zoom_out":
            self.image_display.zoom_out()
        elif action_name == "rotate_cw":
            self.image_display.rotate_clockwise()
        elif action_name == "rotate_ccw":
            self.image_display.rotate_counterclockwise()
        elif action_name == "toggle_fit_mode":
            self.image_display.toggle_fit_mode()
        elif action_name == "reset_view":
            self.image_display.reset_transforms()
        elif action_name == "gif_play_pause":
            if self.image_display.is_animated_gif:
                if self.image_display.is_gif_playing():
                    self.image_display.pause_gif()
                else:
                    self.image_display.resume_gif()
    
    def _handle_tag_action(self, action_name: str, context: dict):
        """Handle tag management keyboard actions."""
        if action_name == "tag_image":
            self._show_tag_dialog()
        elif action_name == "copy_tags":
            self.navigation_controller.copy_tags_from_current()
        elif action_name == "paste_tags":
            self.navigation_controller.paste_tags_to_current()
        elif action_name == "apply_custom_tag":
            tag_spec = context.get('tag_spec', '')
            self.navigation_controller.apply_custom_tag(tag_spec)
            self._update_tags_display()
    
    def _handle_file_action(self, action_name: str, context: dict):
        """Handle file operation keyboard actions."""
        if action_name == "mark_for_deletion":
            self.navigation_controller.mark_for_deletion()
        elif action_name == "delete_marked":
            self._delete_marked_files()
        elif action_name == "undo_action":
            self.navigation_controller.undo_last_action()
        elif action_name == "open_directory":
            self._open_directory()
    
    def _handle_view_action(self, action_name: str, context: dict):
        """Handle view/window keyboard actions."""
        if action_name == "toggle_fullscreen":
            self._toggle_fullscreen()
        elif action_name == "start_slideshow":
            self._start_slideshow()
        elif action_name == "exit_fullscreen":
            if self.isFullScreen():
                self.showNormal()
        elif action_name == "show_help":
            self._show_shortcuts_help()
        elif action_name == "toggle_info_panel":
            self._toggle_info_panel()
    
    # UI update methods
    def _update_image_info(self, image_model):
        """Update the image information panel."""
        info_lines = [
            f"File: {os.path.basename(image_model.file_path)}",
            f"Path: {image_model.file_path}"
        ]
        
        if hasattr(image_model, 'width') and image_model.width and hasattr(image_model, 'height') and image_model.height:
            info_lines.append(f"Size: {image_model.width}x{image_model.height}")
        
        if hasattr(image_model, 'file_size') and image_model.file_size:
            size_mb = image_model.file_size / (1024 * 1024)
            info_lines.append(f"File Size: {size_mb:.1f} MB")
        
        if hasattr(image_model, 'date_taken') and image_model.date_taken:
            info_lines.append(f"Date Taken: {image_model.date_taken}")
        
        if hasattr(image_model, 'photographer') and image_model.photographer:
            info_lines.append(f"Photographer: {image_model.photographer}")
        
        self.info_text.setText('\n'.join(info_lines))
        self._update_tags_display()
    
    def _update_tags_display(self):
        """Update the tags list display."""
        self.tags_list.clear()
        
        if not self.tag_manager:
            return
        
        try:
            current_image = self.navigation_controller.get_current_image()
            if current_image and hasattr(current_image, 'id') and current_image.id:
                with self.db_manager.get_session() as session:
                    image = session.query(ImageModel).get(current_image.id)
                    if image:
                        tags_dict = self.tag_manager.get_image_tags(session, image)
                        
                        for category, tag_names in tags_dict.items():
                            for tag_name in tag_names:
                                self.tags_list.addItem(f"{category}: {tag_name}")
                    else:
                        print(f"Image with id {current_image.id} not found in database")
            else:
                print("Current image has no database ID (fallback mode)")
                            
        except Exception as e:
            print(f"Error updating tags display: {e}")
    
    # Menu action methods
    def _open_directory(self):
        """Open directory dialog."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Photo Directory", self.directory_path or ""
        )
        if directory:
            self.navigation_controller.load_directory(directory)
    
    def _scan_directory(self):
        """Scan current directory for new images."""
        if not self.directory_path:
            self._show_error("Scan Error", "No directory selected")
            return
        
        self._show_info("Scan", "Directory scanning not yet implemented")
    
    def _show_export_dialog(self):
        """Show export dialog."""
        if show_export_dialog(self.db_manager, self.tag_manager, self.directory_path, self):
            self.status_bar.showMessage("Export completed")
    
    def _show_tag_dialog(self):
        """Show tag management dialog for current image."""
        current_image = self.navigation_controller.get_current_image()
        if not current_image:
            return
        
        if hasattr(current_image, 'id') and current_image.id:
            image_dict = {
                'id': current_image.id,
                'file_path': current_image.file_path,
                'filename': current_image.filename
            }
            
            if show_tag_management_dialog(image_dict, self.tag_manager, self):
                self._update_tags_display()
        else:
            self._show_info("Tag Error", "Cannot tag image - no database record")
    
    def _remove_selected_tag(self):
        """Remove selected tag from tags list."""
        selected_items = self.tags_list.selectedItems()
        if not selected_items or not self.tag_manager:
            return
        
        try:
            current_image = self.navigation_controller.get_current_image()
            if not current_image or not hasattr(current_image, 'id') or not current_image.id:
                return
            
            with self.db_manager.get_session() as session:
                image = session.query(ImageModel).get(current_image.id)
                if not image:
                    return
                
                for item in selected_items:
                    tag_text = item.text()
                    if ': ' in tag_text:
                        category, tag_name = tag_text.split(': ', 1)
                        self.db_manager.remove_tag_from_image(session, image, category, tag_name)
                
                session.commit()
            
            self._update_tags_display()
            self.status_bar.showMessage("Removed selected tags")
            
        except Exception as e:
            self._show_error("Tag Error", f"Failed to remove tag: {e}")
    
    def _search_images(self):
        """Show search dialog."""
        query = show_query_builder(self.tag_manager, self)
        if query:
            self.navigation_controller.apply_filter(query)
    
    def _find_duplicates(self):
        """Find and show duplicate images."""
        self._show_info("Duplicates", "Duplicate detection not yet implemented")
    
    def _show_db_stats(self):
        """Show database statistics."""
        show_database_maintenance(self.db_manager, self)
    
    def _show_shortcuts_help(self):
        """Show keyboard shortcuts help."""
        help_dialog = ShortcutHelpDialog(self.keyboard_handler, self)
        help_dialog.exec()
    
    # Direct action methods
    def _next_image(self):
        """Navigate to next image."""
        self.navigation_controller.next_image()
    
    def _previous_image(self):
        """Navigate to previous image."""
        self.navigation_controller.previous_image()
    
    def _zoom_in(self):
        """Zoom in on current image."""
        self.image_display.zoom_in()
    
    def _zoom_out(self):
        """Zoom out on current image."""
        self.image_display.zoom_out()
    
    def _reset_view(self):
        """Reset image view."""
        self.image_display.reset_transforms()
    
    def _copy_tags(self):
        """Copy tags from current image."""
        self.navigation_controller.copy_tags_from_current()
    
    def _paste_tags(self):
        """Paste tags to current image."""
        self.navigation_controller.paste_tags_to_current()
    
    def _toggle_fullscreen(self):
        """Toggle fullscreen mode with clean image-only view."""
        if self.isFullScreen():
            self.showNormal()
            # Show all UI elements when exiting fullscreen
            info_widget = self.splitter.widget(1)
            info_widget.show()
            self.menuBar().show()
            self.statusBar().show()
            self.keyboard_handler.set_context_mode('normal')
        else:
            self.showFullScreen()
            # Hide all UI elements for clean fullscreen image viewing
            info_widget = self.splitter.widget(1)
            info_widget.hide()
            self.menuBar().hide()
            self.statusBar().hide()
            self.keyboard_handler.set_context_mode('fullscreen')
    
    def _start_slideshow(self):
        """Start slideshow mode."""
        images = self.navigation_controller.current_images
        if not images:
            self._show_info("Slideshow", "No images to display")
            return
        
        try:
            # Convert ImageModel objects to dictionaries for slideshow
            image_dicts = []
            for img in images:
                image_dict = {
                    'file_path': img.file_path,
                    'filename': img.filename
                }
                
                # Add optional fields if they exist
                if hasattr(img, 'date_taken') and img.date_taken:
                    image_dict['date_taken'] = img.date_taken
                
                image_dicts.append(image_dict)
            
            slideshow_widget = start_slideshow(image_dicts, self.config)
            slideshow_widget.slideshow_ended.connect(self._on_slideshow_ended)
            slideshow_widget.show()
            
            self.hide()
            
        except Exception as e:
            self._show_error("Slideshow Error", f"Failed to start slideshow: {e}")
    
    def _on_slideshow_ended(self):
        """Handle slideshow ending."""
        self.show()
        self.keyboard_handler.set_context_mode('normal')
    
    def _delete_marked_files(self):
        """Delete files marked for deletion."""
        marked_files = self.navigation_controller.get_marked_files()
        if not marked_files:
            self._show_info("Delete", "No files marked for deletion")
            return
        
        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"Delete {len(marked_files)} marked files?\n\nFiles will be moved to trash.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            success = self.navigation_controller.delete_marked_files(move_to_trash=True)
            if success:
                self.status_bar.showMessage("Files moved to trash")
            else:
                self._show_error("Delete Error", "Some files could not be deleted")
    
    def _toggle_info_panel(self):
        """Toggle visibility of the info panel."""
        info_widget = self.splitter.widget(1)
        if info_widget.isVisible():
            info_widget.hide()
        else:
            info_widget.show()
    
    # Utility methods
    def _show_error(self, title: str, message: str):
        """Show error message dialog."""
        QMessageBox.critical(self, title, message)
    
    def _show_info(self, title: str, message: str):
        """Show information message dialog."""
        QMessageBox.information(self, title, message)
    
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
            border-bottom: 1px solid #555555;
        }
        QMenuBar::item {
            background-color: transparent;
            padding: 4px 8px;
        }
        QMenuBar::item:selected {
            background-color: #555555;
        }
        QStatusBar {
            background-color: #3c3c3c;
            color: #ffffff;
            border-top: 1px solid #555555;
        }
        QLabel {
            color: #ffffff;
        }
        QTextEdit {
            background-color: #404040;
            color: #ffffff;
            border: 1px solid #555555;
        }
        QListWidget {
            background-color: #404040;
            color: #ffffff;
            border: 1px solid #555555;
        }
        QListWidget::item:selected {
            background-color: #0078d4;
        }
        QPushButton {
            background-color: #0078d4;
            color: #ffffff;
            border: none;
            padding: 6px 12px;
            border-radius: 3px;
        }
        QPushButton:hover {
            background-color: #106ebe;
        }
        QPushButton:pressed {
            background-color: #005a9e;
        }
        QFrame {
            border: 1px solid #555555;
        }
        QSplitter::handle {
            background-color: #555555;
        }
        """
        self.setStyleSheet(dark_stylesheet)
    
    def closeEvent(self, event):
        """Handle application close event."""
        try:
            # Stop any background operations
            if hasattr(self.image_display, 'image_loader') and self.image_display.image_loader:
                if self.image_display.image_loader.isRunning():
                    self.image_display.image_loader.stop()
                    self.image_display.image_loader.wait(1000)
            
            # Clean up database connections
            if self.db_manager and hasattr(self.db_manager, 'close_connection'):
                self.db_manager.close_connection()
            
        except Exception as e:
            print(f"Error during cleanup: {e}")
        
        event.accept()


def create_qt_application():
    """Create Qt application instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    app.setApplicationName("Photo Manager")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Photo Manager")
    
    return app


def main():
    """Main entry point for Qt application."""
    app = create_qt_application()
    
    directory = None
    slideshow = False
    
    if len(sys.argv) > 1:
        directory = sys.argv[1]
        if '--slideshow' in sys.argv:
            slideshow = True
    
    try:
        window = MainWindow(
            directory_path=directory,
            slideshow_mode=slideshow
        )
        window.show()
        
        return app.exec()
        
    except Exception as e:
        print(f"Failed to start application: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())