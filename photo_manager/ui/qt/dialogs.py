"""
Qt dialog windows for the photo manager application.
Includes tag management, export configuration, and other utility dialogs.
"""

import os
from typing import Optional, List, Dict, Any, Tuple

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QLineEdit, QComboBox, QListWidget, QTextEdit, QCheckBox,
    QGroupBox, QFormLayout, QSpinBox, QDoubleSpinBox,
    QFileDialog, QMessageBox, QProgressDialog, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QPixmap


class TagManagementDialog(QDialog):
    """Dialog for managing tags on images."""
    
    tags_changed = Signal()
    
    def __init__(self, image_info: Dict[str, Any], tag_manager, parent=None):
        super().__init__(parent)
        
        self.image_info = image_info
        self.tag_manager = tag_manager
        self.current_tags = []
        
        self._init_ui()
        self._load_current_tags()
    
    def _init_ui(self):
        """Initialize the dialog UI."""
        self.setWindowTitle("Manage Tags")
        self.setModal(True)
        self.resize(400, 500)
        
        layout = QVBoxLayout(self)
        
        # Image info
        image_info_label = QLabel(f"Image: {os.path.basename(self.image_info['file_path'])}")
        image_info_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(image_info_label)
        
        # Current tags
        current_tags_group = QGroupBox("Current Tags")
        current_tags_layout = QVBoxLayout(current_tags_group)
        
        self.current_tags_list = QListWidget()
        current_tags_layout.addWidget(self.current_tags_list)
        
        # Remove tag button
        remove_button = QPushButton("Remove Selected Tag")
        remove_button.clicked.connect(self._remove_selected_tag)
        current_tags_layout.addWidget(remove_button)
        
        layout.addWidget(current_tags_group)
        
        # Add new tag
        add_tag_group = QGroupBox("Add New Tag")
        add_tag_layout = QFormLayout(add_tag_group)
        
        self.category_combo = QComboBox()
        self.category_combo.addItems([
            "favorites", "to_delete", "scene_tags", 
            "event_tags", "people_tags"
        ])
        self.category_combo.setCurrentText("scene_tags")
        
        self.tag_name_edit = QLineEdit()
        self.tag_name_edit.returnPressed.connect(self._add_tag)
        
        add_tag_layout.addRow("Category:", self.category_combo)
        add_tag_layout.addRow("Tag Name:", self.tag_name_edit)
        
        add_tag_button = QPushButton("Add Tag")
        add_tag_button.clicked.connect(self._add_tag)
        add_tag_layout.addWidget(add_tag_button)
        
        layout.addWidget(add_tag_group)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _load_current_tags(self):
        """Load current tags for the image."""
        if not self.tag_manager:
            return
        
        try:
            self.current_tags = self.tag_manager.get_image_tags(self.image_info['id'])
            self._refresh_tags_list()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load tags: {e}")
    
    def _refresh_tags_list(self):
        """Refresh the current tags list display."""
        self.current_tags_list.clear()
        for tag in self.current_tags:
            self.current_tags_list.addItem(f"{tag['category']}: {tag['name']}")
    
    def _add_tag(self):
        """Add a new tag to the image."""
        category = self.category_combo.currentText()
        tag_name = self.tag_name_edit.text().strip()
        
        if not tag_name:
            QMessageBox.warning(self, "Invalid Input", "Please enter a tag name")
            return
        
        try:
            self.tag_manager.add_tag_to_image(
                self.image_info['id'], category, tag_name
            )
            self.tag_name_edit.clear()
            self._load_current_tags()  # Refresh display
            self.tags_changed.emit()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add tag: {e}")
    
    def _remove_selected_tag(self):
        """Remove selected tag from the image."""
        selected_items = self.current_tags_list.selectedItems()
        if not selected_items:
            return
        
        try:
            for item in selected_items:
                tag_text = item.text()
                if ': ' in tag_text:
                    category, tag_name = tag_text.split(': ', 1)
                    self.tag_manager.remove_tag_from_image(
                        self.image_info['id'], category, tag_name
                    )
            
            self._load_current_tags()  # Refresh display
            self.tags_changed.emit()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to remove tag: {e}")


class ExportPreviewDialog(QDialog):
    """Dialog for previewing and configuring export operations."""
    
    def __init__(self, db_manager, tag_manager, parent=None):
        super().__init__(parent)
        
        self.db_manager = db_manager
        self.tag_manager = tag_manager
        self.preview_results = []
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the export preview dialog."""
        self.setWindowTitle("Export Images")
        self.setModal(True)
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # Export configuration
        config_group = QGroupBox("Export Configuration")
        config_layout = QFormLayout(config_group)
        
        # Query input
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("e.g., event_tags:birthday AND people_tags:child1")
        config_layout.addRow("Filter Query:", self.query_edit)
        
        # Export path
        path_layout = QHBoxLayout()
        self.export_path_edit = QLineEdit()
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_export_path)
        path_layout.addWidget(self.export_path_edit)
        path_layout.addWidget(browse_button)
        config_layout.addRow("Export Path:", path_layout)
        
        # Directory structure
        self.structure_edit = QLineEdit()
        self.structure_edit.setText("{year}/{event_tags}")
        self.structure_edit.setPlaceholderText("e.g., {year}/{event_tags} or flat")
        config_layout.addRow("Directory Structure:", self.structure_edit)
        
        # Operation type
        self.operation_combo = QComboBox()
        self.operation_combo.addItems(["copy", "move"])
        config_layout.addRow("Operation:", self.operation_combo)
        
        # Export database checkbox
        self.export_db_checkbox = QCheckBox("Export subset database")
        self.export_db_checkbox.setToolTip("Create a database with only exported images")
        config_layout.addWidget(self.export_db_checkbox)
        
        layout.addWidget(config_group)
        
        # Preview button
        preview_button = QPushButton("Preview Export")
        preview_button.clicked.connect(self._preview_export)
        layout.addWidget(preview_button)
        
        # Preview results
        preview_group = QGroupBox("Export Preview")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(3)
        self.preview_table.setHorizontalHeaderLabels(["Source", "Target", "Status"])
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        preview_layout.addWidget(self.preview_table)
        
        self.preview_summary = QLabel("No preview available")
        preview_layout.addWidget(self.preview_summary)
        
        layout.addWidget(preview_group)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._execute_export)
        button_box.rejected.connect(self.reject)
        
        self.export_button = button_box.button(QDialogButtonBox.Ok)
        self.export_button.setText("Execute Export")
        self.export_button.setEnabled(False)
        
        layout.addWidget(button_box)
    
    def _browse_export_path(self):
        """Browse for export directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Export Directory"
        )
        if directory:
            self.export_path_edit.setText(directory)
    
    def _preview_export(self):
        """Preview the export operation."""
        query = self.query_edit.text().strip()
        export_path = self.export_path_edit.text().strip()
        structure = self.structure_edit.text().strip()
        
        if not export_path:
            QMessageBox.warning(self, "Invalid Input", "Please select an export path")
            return
        
        try:
            # TODO: Implement actual preview logic with database query
            # For now, show placeholder
            self.preview_results = [
                {
                    'source': '/path/to/image1.jpg',
                    'target': f'{export_path}/2024/birthday/image1.jpg',
                    'status': 'Ready'
                },
                {
                    'source': '/path/to/image2.jpg', 
                    'target': f'{export_path}/2024/birthday/image2.jpg',
                    'status': 'Ready'
                }
            ]
            
            self._update_preview_display()
            self.export_button.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Preview Error", f"Failed to preview export: {e}")
    
    def _update_preview_display(self):
        """Update the preview table display."""
        self.preview_table.setRowCount(len(self.preview_results))
        
        for row, result in enumerate(self.preview_results):
            self.preview_table.setItem(row, 0, QTableWidgetItem(result['source']))
            self.preview_table.setItem(row, 1, QTableWidgetItem(result['target']))
            self.preview_table.setItem(row, 2, QTableWidgetItem(result['status']))
        
        # Update summary
        total_files = len(self.preview_results)
        total_size = 0  # TODO: Calculate actual size
        
        summary_text = f"Files to export: {total_files}\nEstimated size: {total_size} MB"
        self.preview_summary.setText(summary_text)
    
    def _execute_export(self):
        """Execute the export operation."""
        if not self.preview_results:
            QMessageBox.warning(self, "No Preview", "Please preview the export first")
            return
        
        # TODO: Implement actual export execution
        QMessageBox.information(self, "Export", "Export functionality not yet implemented")
        self.accept()


class DuplicateViewerDialog(QDialog):
    """Dialog for viewing and managing duplicate images."""
    
    def __init__(self, duplicate_groups: List[List[Dict[str, Any]]], parent=None):
        super().__init__(parent)
        
        self.duplicate_groups = duplicate_groups
        self.current_group_index = 0
        
        self._init_ui()
        self._display_current_group()
    
    def _init_ui(self):
        """Initialize the duplicate viewer dialog."""
        self.setWindowTitle("Duplicate Images")
        self.setModal(True)
        self.resize(900, 700)
        
        layout = QVBoxLayout(self)
        
        # Navigation
        nav_layout = QHBoxLayout()
        
        self.prev_group_btn = QPushButton("Previous Group")
        self.prev_group_btn.clicked.connect(self._previous_group)
        
        self.group_label = QLabel()
        self.group_label.setAlignment(Qt.AlignCenter)
        
        self.next_group_btn = QPushButton("Next Group")
        self.next_group_btn.clicked.connect(self._next_group)
        
        nav_layout.addWidget(self.prev_group_btn)
        nav_layout.addWidget(self.group_label)
        nav_layout.addWidget(self.next_group_btn)
        
        layout.addLayout(nav_layout)
        
        # Duplicate images display
        self.duplicates_table = QTableWidget()
        self.duplicates_table.setColumnCount(4)
        self.duplicates_table.setHorizontalHeaderLabels([
            "Preview", "Filename", "Size", "Action"
        ])
        self.duplicates_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.duplicates_table)
        
        # Action buttons
        action_layout = QHBoxLayout()
        
        keep_first_btn = QPushButton("Keep First, Delete Others")
        keep_first_btn.clicked.connect(self._keep_first_delete_others)
        
        keep_largest_btn = QPushButton("Keep Largest, Delete Others")
        keep_largest_btn.clicked.connect(self._keep_largest_delete_others)
        
        action_layout.addWidget(keep_first_btn)
        action_layout.addWidget(keep_largest_btn)
        action_layout.addStretch()
        
        layout.addLayout(action_layout)
        
        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _display_current_group(self):
        """Display the current duplicate group."""
        if not self.duplicate_groups:
            return
        
        group = self.duplicate_groups[self.current_group_index]
        self.group_label.setText(f"Group {self.current_group_index + 1} of {len(self.duplicate_groups)}")
        
        # Update navigation buttons
        self.prev_group_btn.setEnabled(self.current_group_index > 0)
        self.next_group_btn.setEnabled(self.current_group_index < len(self.duplicate_groups) - 1)
        
        # Populate table
        self.duplicates_table.setRowCount(len(group))
        
        for row, image_info in enumerate(group):
            # Preview (thumbnail)
            preview_label = QLabel()
            try:
                pixmap = QPixmap(image_info['file_path'])
                if not pixmap.isNull():
                    thumbnail = pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    preview_label.setPixmap(thumbnail)
                else:
                    preview_label.setText("No preview")
            except:
                preview_label.setText("Error")
            
            self.duplicates_table.setCellWidget(row, 0, preview_label)
            
            # Filename
            filename = os.path.basename(image_info['file_path'])
            self.duplicates_table.setItem(row, 1, QTableWidgetItem(filename))
            
            # Size
            size_mb = image_info.get('file_size', 0) / (1024 * 1024)
            self.duplicates_table.setItem(row, 2, QTableWidgetItem(f"{size_mb:.1f} MB"))
            
            # Action buttons
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 2, 2, 2)
            
            keep_btn = QPushButton("Keep")
            delete_btn = QPushButton("Delete")
            
            action_layout.addWidget(keep_btn)
            action_layout.addWidget(delete_btn)
            
            self.duplicates_table.setCellWidget(row, 3, action_widget)
    
    def _previous_group(self):
        """Go to previous duplicate group."""
        if self.current_group_index > 0:
            self.current_group_index -= 1
            self._display_current_group()
    
    def _next_group(self):
        """Go to next duplicate group."""
        if self.current_group_index < len(self.duplicate_groups) - 1:
            self.current_group_index += 1
            self._display_current_group()
    
    def _keep_first_delete_others(self):
        """Keep first image, mark others for deletion."""
        # TODO: Implement duplicate resolution logic
        QMessageBox.information(self, "Action", "Keep first functionality not yet implemented")
    
    def _keep_largest_delete_others(self):
        """Keep largest image, mark others for deletion."""
        # TODO: Implement duplicate resolution logic
        QMessageBox.information(self, "Action", "Keep largest functionality not yet implemented")


class SearchDialog(QDialog):
    """Dialog for searching images with advanced query options."""
    
    def __init__(self, tag_manager, parent=None):
        super().__init__(parent)
        
        self.tag_manager = tag_manager
        self.search_results = []
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the search dialog."""
        self.setWindowTitle("Search Images")
        self.setModal(True)
        self.resize(600, 500)
        
        layout = QVBoxLayout(self)
        
        # Search input
        search_group = QGroupBox("Search Query")
        search_layout = QVBoxLayout(search_group)
        
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("Enter search query...")
        self.query_edit.returnPressed.connect(self._execute_search)
        search_layout.addWidget(self.query_edit)
        
        # Query examples
        examples_label = QLabel("""
Examples:
• event_tags:birthday
• people_tags:child1 AND scene_tags:outdoor
• favorites:true OR event_tags:vacation
• date_taken:2024
        """)
        examples_label.setStyleSheet("font-size: 10px; color: gray;")
        search_layout.addWidget(examples_label)
        
        # Search button
        search_button = QPushButton("Search")
        search_button.clicked.connect(self._execute_search)
        search_layout.addWidget(search_button)
        
        layout.addWidget(search_group)
        
        # Results
        results_group = QGroupBox("Search Results")
        results_layout = QVBoxLayout(results_group)
        
        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self._open_selected_image)
        results_layout.addWidget(self.results_list)
        
        self.results_summary = QLabel("No search performed")
        results_layout.addWidget(self.results_summary)
        
        layout.addWidget(results_group)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _execute_search(self):
        """Execute the search query."""
        query = self.query_edit.text().strip()
        if not query:
            return
        
        try:
            # TODO: Implement actual search logic
            # Placeholder results
            self.search_results = [
                {'file_path': '/example/path1.jpg', 'filename': 'image1.jpg'},
                {'file_path': '/example/path2.jpg', 'filename': 'image2.jpg'}
            ]
            
            self._update_results_display()
            
        except Exception as e:
            QMessageBox.critical(self, "Search Error", f"Search failed: {e}")
    
    def _update_results_display(self):
        """Update the search results display."""
        self.results_list.clear()
        
        for result in self.search_results:
            filename = os.path.basename(result['file_path'])
            self.results_list.addItem(filename)
        
        count = len(self.search_results)
        self.results_summary.setText(f"Found {count} matching images")
    
    def _open_selected_image(self, item):
        """Open selected image in main viewer."""
        # TODO: Signal main window to open selected image
        pass
    
    def get_selected_images(self) -> List[Dict[str, Any]]:
        """Get the search results."""
        return self.search_results


class DatabaseStatsDialog(QDialog):
    """Dialog showing database statistics and health information."""
    
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        
        self.db_manager = db_manager
        self._init_ui()
        self._load_statistics()
    
    def _init_ui(self):
        """Initialize the statistics dialog."""
        self.setWindowTitle("Database Statistics")
        self.setModal(True)
        self.resize(500, 400)
        
        layout = QVBoxLayout(self)
        
        # Statistics display
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        layout.addWidget(self.stats_text)
        
        # Action buttons
        action_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_statistics)
        
        optimize_btn = QPushButton("Optimize Database")
        optimize_btn.clicked.connect(self._optimize_database)
        
        action_layout.addWidget(refresh_btn)
        action_layout.addWidget(optimize_btn)
        action_layout.addStretch()
        
        layout.addLayout(action_layout)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
    
    def _load_statistics(self):
        """Load and display database statistics."""
        try:
            # TODO: Get actual statistics from database
            stats_text = """Database Statistics:

Total Images: 1,234
Total Tags: 567
Unique Tags: 89

By Category:
• Scene Tags: 234
• Event Tags: 123
• People Tags: 89
• Favorites: 45
• To Delete: 12

File Status:
• Valid Images: 1,200
• Corrupt Images: 15
• Missing Files: 19

Storage:
• Database Size: 2.5 MB
• Total Image Size: 15.2 GB
• Average File Size: 12.3 MB

Duplicates:
• Potential Duplicates: 23 groups
• Total Duplicate Files: 67
"""
            
            self.stats_text.setText(stats_text)
            
        except Exception as e:
            self.stats_text.setText(f"Error loading statistics: {e}")
    
    def _optimize_database(self):
        """Optimize the database."""
        try:
            # TODO: Implement database optimization
            QMessageBox.information(self, "Optimize", "Database optimization not yet implemented")
        except Exception as e:
            QMessageBox.critical(self, "Optimization Error", f"Failed to optimize: {e}")


class ConfigurationDialog(QDialog):
    """Dialog for editing application configuration."""
    
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        
        self.config_manager = config_manager
        self.config = config_manager.get_current_config() if config_manager else {}
        
        self._init_ui()
        self._load_config_values()
    
    def _init_ui(self):
        """Initialize the configuration dialog."""
        self.setWindowTitle("Configuration")
        self.setModal(True)
        self.resize(500, 600)
        
        layout = QVBoxLayout(self)
        
        # Tabbed interface
        tabs = QTabWidget()
        
        # UI Settings tab
        ui_tab = QWidget()
        ui_layout = QFormLayout(ui_tab)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["light", "dark"])
        ui_layout.addRow("Theme:", self.theme_combo)
        
        self.start_fullscreen_check = QCheckBox()
        ui_layout.addRow("Start Fullscreen:", self.start_fullscreen_check)
        
        self.default_zoom_combo = QComboBox()
        self.default_zoom_combo.addItems(["fit_to_window", "actual_size", "fill_window"])
        ui_layout.addRow("Default Zoom:", self.default_zoom_combo)
        
        tabs.addTab(ui_tab, "UI Settings")
        
        # Slideshow Settings tab
        slideshow_tab = QWidget()
        slideshow_layout = QFormLayout(slideshow_tab)
        
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0.5, 60.0)
        self.duration_spin.setSuffix(" seconds")
        slideshow_layout.addRow("Slide Duration:", self.duration_spin)
        
        self.transition_combo = QComboBox()
        self.transition_combo.addItems(["fade", "wipe", "replace"])
        slideshow_layout.addRow("Transition:", self.transition_combo)
        
        self.random_order_check = QCheckBox()
        slideshow_layout.addRow("Random Order:", self.random_order_check)
        
        tabs.addTab(slideshow_tab, "Slideshow")
        
        # Database Settings tab
        db_tab = QWidget()
        db_layout = QFormLayout(db_tab)
        
        self.db_type_combo = QComboBox()
        self.db_type_combo.addItems(["sqlite", "postgresql", "mysql"])
        db_layout.addRow("Database Type:", self.db_type_combo)
        
        self.db_path_edit = QLineEdit()
        db_layout.addRow("Database Path:", self.db_path_edit)
        
        tabs.addTab(db_tab, "Database")
        
        layout.addWidget(tabs)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.Apply).clicked.connect(self._apply_changes)
        
        layout.addWidget(button_box)
    
    def _load_config_values(self):
        """Load current configuration values into the dialog."""
        ui_config = self.config.get('ui', {})
        self.theme_combo.setCurrentText(ui_config.get('theme', 'light'))
        self.start_fullscreen_check.setChecked(ui_config.get('start_fullscreen', False))
        self.default_zoom_combo.setCurrentText(ui_config.get('default_zoom', 'fit_to_window'))
        
        slideshow_config = self.config.get('slideshow', {})
        self.duration_spin.setValue(slideshow_config.get('duration', 5.0))
        self.transition_combo.setCurrentText(slideshow_config.get('transition', 'fade'))
        self.random_order_check.setChecked(slideshow_config.get('random_order', False))
        
        db_config = self.config.get('database', {})
        self.db_type_combo.setCurrentText(db_config.get('type', 'sqlite'))
        self.db_path_edit.setText(db_config.get('path', '.photo_manager.db'))
    
    def _apply_changes(self):
        """Apply configuration changes."""
        try:
            # Update config dictionary
            self.config['ui'] = {
                'theme': self.theme_combo.currentText(),
                'start_fullscreen': self.start_fullscreen_check.isChecked(),
                'default_zoom': self.default_zoom_combo.currentText()
            }
            
            self.config['slideshow'] = {
                'duration': self.duration_spin.value(),
                'transition': self.transition_combo.currentText(),
                'random_order': self.random_order_check.isChecked()
            }
            
            self.config['database'] = {
                'type': self.db_type_combo.currentText(),
                'path': self.db_path_edit.text()
            }
            
            # Save configuration
            if self.config_manager:
                self.config_manager.save_config(self.config)
            
            QMessageBox.information(self, "Success", "Configuration saved successfully")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration: {e}")
    
    def accept(self):
        """Accept dialog and apply changes."""
        self._apply_changes()
        super().accept()


class ProgressDialog(QProgressDialog):
    """Custom progress dialog for long-running operations."""
    
    def __init__(self, title: str, operation: str, parent=None):
        super().__init__(operation, "Cancel", 0, 100, parent)
        
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumDuration(1000)  # Show after 1 second
        
        # Customize appearance
        self.setFixedSize(400, 120)
    
    def update_progress(self, value: int, text: Optional[str] = None):
        """Update progress value and optional text."""
        self.setValue(value)
        if text:
            self.setLabelText(text)

def show_tag_management_dialog(image_info: Dict[str, Any], tag_manager, parent=None) -> bool:
    """
    Show tag management dialog for an image.
    
    Returns:
        bool: True if tags were modified, False otherwise
    """
    dialog = TagManagementDialog(image_info, tag_manager, parent)
    result = dialog.exec()
    return result == QDialog.Accepted


def show_export_dialog(db_manager, tag_manager, current_directory: str = None, parent=None) -> bool:
    """
    Show export preview dialog.
    
    Returns:
        bool: True if export was executed, False otherwise
    """
    dialog = ExportPreviewDialog(db_manager, tag_manager, parent)
    result = dialog.exec()
    return result == QDialog.Accepted


def show_query_builder(tag_manager, parent=None) -> Optional[str]:
    """
    Show query builder dialog.
    
    Returns:
        str: Built query string, or None if cancelled
    """
    dialog = SearchDialog(tag_manager, parent)
    if dialog.exec() == QDialog.Accepted:
        return dialog.query_edit.text().strip()
    return None


def show_database_maintenance(db_manager, parent=None):
    """Show database maintenance dialog."""
    dialog = DatabaseStatsDialog(db_manager, parent)
    dialog.exec()