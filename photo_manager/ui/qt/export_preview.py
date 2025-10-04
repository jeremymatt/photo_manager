"""
Qt export preview dialog for the photo manager application.
Provides detailed preview and configuration for export operations.
"""

import os
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QLineEdit, QComboBox, QListWidget, QTextEdit, QCheckBox,
    QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QProgressDialog, QHeaderView,
    QDialogButtonBox, QSplitter, QFrame
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QPixmap, QFont


class ExportWorker(QThread):
    """Background worker for export operations."""
    
    progress_updated = Signal(int, str)  # percentage, current_file
    export_completed = Signal(bool, str)  # success, message
    
    def __init__(self, export_plan: List[Dict[str, Any]], operation: str):
        super().__init__()
        self.export_plan = export_plan
        self.operation = operation  # 'copy' or 'move'
        self.should_stop = False
    
    def run(self):
        """Execute the export operation."""
        try:
            total_files = len(self.export_plan)
            
            for i, item in enumerate(self.export_plan):
                if self.should_stop:
                    break
                
                source_path = item['source_path']
                target_path = item['target_path']
                
                # Emit progress
                filename = os.path.basename(source_path)
                self.progress_updated.emit(
                    int((i + 1) / total_files * 100), 
                    f"Processing: {filename}"
                )
                
                # Create target directory if needed
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                
                # Copy or move file
                if self.operation == 'copy':
                    import shutil
                    shutil.copy2(source_path, target_path)
                elif self.operation == 'move':
                    import shutil
                    shutil.move(source_path, target_path)
            
            if not self.should_stop:
                self.export_completed.emit(True, f"Successfully exported {total_files} files")
            else:
                self.export_completed.emit(False, "Export cancelled by user")
                
        except Exception as e:
            self.export_completed.emit(False, f"Export failed: {str(e)}")
    
    def stop(self):
        """Stop the export operation."""
        self.should_stop = True


class ExportPreviewDialog(QDialog):
    """Dialog for previewing and executing export operations."""
    
    def __init__(self, db_manager, tag_manager, current_directory: str = None, parent=None):
        super().__init__(parent)
        
        self.db_manager = db_manager
        self.tag_manager = tag_manager
        self.current_directory = current_directory
        self.export_plan = []
        self.export_worker = None
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the export preview dialog."""
        self.setWindowTitle("Export Images")
        self.setModal(True)
        self.resize(1000, 700)
        
        # Main layout with splitter
        main_layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(splitter)
        
        # Configuration section
        config_widget = self._create_config_section()
        splitter.addWidget(config_widget)
        
        # Preview section
        preview_widget = self._create_preview_section()
        splitter.addWidget(preview_widget)
        
        # Set splitter proportions
        splitter.setSizes([250, 450])
        
        # Dialog buttons
        button_layout = QHBoxLayout()
        
        self.preview_btn = QPushButton("Generate Preview")
        self.preview_btn.clicked.connect(self._generate_preview)
        
        self.export_btn = QPushButton("Execute Export")
        self.export_btn.clicked.connect(self._execute_export)
        self.export_btn.setEnabled(False)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(self.preview_btn)
        button_layout.addWidget(self.export_btn)
        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        
        main_layout.addLayout(button_layout)
    
    def _create_config_section(self) -> QWidget:
        """Create the configuration section."""
        config_widget = QFrame()
        config_widget.setFrameStyle(QFrame.StyledPanel)
        layout = QVBoxLayout(config_widget)
        
        # Title
        title_label = QLabel("Export Configuration")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Configuration form
        form_layout = QFormLayout()
        
        # Query input
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("e.g., event_tags:birthday AND people_tags:child1")
        form_layout.addRow("Filter Query:", self.query_edit)
        
        # Export path
        path_layout = QHBoxLayout()
        self.export_path_edit = QLineEdit()
        self.export_path_edit.setText(self.current_directory or "")
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_export_path)
        
        path_layout.addWidget(self.export_path_edit)
        path_layout.addWidget(browse_btn)
        form_layout.addRow("Export Path:", path_layout)
        
        # Directory structure template
        self.structure_edit = QLineEdit()
        self.structure_edit.setText("{year}/{event_tags}")
        self.structure_edit.setPlaceholderText("e.g., {year}/{month} or 'flat' for no subdirectories")
        form_layout.addRow("Directory Structure:", self.structure_edit)
        
        # Operation type
        self.operation_combo = QComboBox()
        self.operation_combo.addItems(["copy", "move"])
        form_layout.addRow("Operation:", self.operation_combo)
        
        # Additional options
        self.export_db_check = QCheckBox("Export subset database")
        self.export_db_check.setToolTip("Create a database containing only exported images")
        form_layout.addRow("Database:", self.export_db_check)
        
        self.preserve_structure_check = QCheckBox("Preserve original structure if template fails")
        self.preserve_structure_check.setChecked(True)
        form_layout.addRow("Fallback:", self.preserve_structure_check)
        
        layout.addLayout(form_layout)
        
        # Query examples
        examples_group = QGroupBox("Query Examples")
        examples_layout = QVBoxLayout(examples_group)
        
        examples_text = QLabel("""
• event_tags:birthday - All birthday photos
• people_tags:child1 AND scene_tags:outdoor - Child1 outdoor photos  
• favorites:true - All favorited images
• date_taken:2024 - All photos from 2024
• event_tags:vacation OR event_tags:trip - Vacation or trip photos
        """)
        examples_text.setStyleSheet("font-size: 10px; color: gray;")
        examples_layout.addWidget(examples_text)
        
        layout.addWidget(examples_group)
        
        return config_widget
    
    def _create_preview_section(self) -> QWidget:
        """Create the preview results section."""
        preview_widget = QFrame()
        preview_widget.setFrameStyle(QFrame.StyledPanel)
        layout = QVBoxLayout(preview_widget)
        
        # Title
        title_label = QLabel("Export Preview")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Summary
        self.summary_label = QLabel("Click 'Generate Preview' to see export results")
        self.summary_label.setStyleSheet("margin-bottom: 10px;")
        layout.addWidget(self.summary_label)
        
        # Preview table
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(4)
        self.preview_table.setHorizontalHeaderLabels([
            "Source File", "Target Path", "Size", "Status"
        ])
        
        # Set column widths
        header = self.preview_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        
        layout.addWidget(self.preview_table)
        
        return preview_widget
    
    def _browse_export_path(self):
        """Browse for export directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Export Directory", self.export_path_edit.text()
        )
        if directory:
            self.export_path_edit.setText(directory)
    
    def _generate_preview(self):
        """Generate export preview."""
        query = self.query_edit.text().strip()
        export_path = self.export_path_edit.text().strip()
        structure_template = self.structure_edit.text().strip()
        
        # Validate inputs
        if not export_path:
            QMessageBox.warning(self, "Invalid Input", "Please select an export path")
            return
        
        if not os.path.exists(export_path):
            reply = QMessageBox.question(
                self, "Create Directory", 
                f"Export path does not exist:\n{export_path}\n\nCreate it?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                try:
                    os.makedirs(export_path, exist_ok=True)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to create directory: {e}")
                    return
            else:
                return
        
        try:
            # Get images matching query
            if self.db_manager:
                # TODO: Implement actual query execution
                matching_images = self._mock_query_results(query)
            else:
                QMessageBox.warning(self, "Database Error", "Database not available")
                return
            
            # Generate export plan
            self.export_plan = []
            total_size = 0
            
            for image in matching_images:
                source_path = image['file_path']
                
                # Generate target path based on template
                target_subpath = self._generate_target_path(image, structure_template)
                target_path = os.path.join(export_path, target_subpath)
                
                # Check for conflicts
                status = "Ready"
                if os.path.exists(target_path):
                    status = "File exists"
                
                file_size = image.get('file_size', 0)
                total_size += file_size
                
                self.export_plan.append({
                    'source_path': source_path,
                    'target_path': target_path,
                    'file_size': file_size,
                    'status': status,
                    'image_info': image
                })
            
            # Update preview display
            self._update_preview_table()
            
            # Update summary
            total_size_mb = total_size / (1024 * 1024)
            conflicts = sum(1 for item in self.export_plan if item['status'] == "File exists")
            
            summary_text = f"Found {len(self.export_plan)} images to export\n"
            summary_text += f"Total size: {total_size_mb:.1f} MB\n"
            if conflicts > 0:
                summary_text += f"⚠️ {conflicts} file conflicts detected"
            
            self.summary_label.setText(summary_text)
            self.export_btn.setEnabled(len(self.export_plan) > 0)
            
        except Exception as e:
            QMessageBox.critical(self, "Preview Error", f"Failed to generate preview: {e}")
    
    def _mock_query_results(self, query: str) -> List[Dict[str, Any]]:
        """Mock query results for testing."""
        # TODO: Replace with actual database query
        return [
            {
                'id': 1,
                'file_path': '/photos/2024/birthday/img001.jpg',
                'filename': 'img001.jpg',
                'file_size': 2548736,  # ~2.5MB
                'date_taken': '2024-03-15',
                'tags': [
                    {'category': 'event_tags', 'name': 'birthday'},
                    {'category': 'people_tags', 'name': 'child1'}
                ]
            },
            {
                'id': 2,
                'file_path': '/photos/2024/birthday/img002.jpg',
                'filename': 'img002.jpg',
                'file_size': 3145728,  # ~3MB
                'date_taken': '2024-03-15',
                'tags': [
                    {'category': 'event_tags', 'name': 'birthday'},
                    {'category': 'people_tags', 'name': 'child2'}
                ]
            }
        ]
    
    def _generate_target_path(self, image_info: Dict[str, Any], template: str) -> str:
        """Generate target path based on template."""
        if template.lower() == 'flat':
            return image_info['filename']
        
        # Parse template variables
        target_path = template
        
        # Replace common variables
        if 'date_taken' in image_info and image_info['date_taken']:
            date_str = str(image_info['date_taken'])
            if len(date_str) >= 4:
                year = date_str[:4]
                target_path = target_path.replace('{year}', year)
            if len(date_str) >= 7:
                month = date_str[5:7]
                target_path = target_path.replace('{month}', month)
        
        # Replace tag variables
        tags = image_info.get('tags', [])
        tag_dict = {}
        for tag in tags:
            category = tag['category']
            if category not in tag_dict:
                tag_dict[category] = []
            tag_dict[category].append(tag['name'])
        
        # Replace tag placeholders
        for category, tag_list in tag_dict.items():
            placeholder = f"{{{category}}}"
            if placeholder in target_path:
                # Use first tag of this category
                target_path = target_path.replace(placeholder, tag_list[0])
        
        # Clean up any remaining placeholders
        import re
        target_path = re.sub(r'\{[^}]+\}', 'untagged', target_path)
        
        # Ensure it ends with filename
        if not target_path.endswith(image_info['filename']):
            target_path = os.path.join(target_path, image_info['filename'])
        
        return target_path
    
    def _update_preview_table(self):
        """Update the preview table with export plan."""
        self.preview_table.setRowCount(len(self.export_plan))
        
        for row, item in enumerate(self.export_plan):
            # Source file (just filename)
            source_name = os.path.basename(item['source_path'])
            self.preview_table.setItem(row, 0, QTableWidgetItem(source_name))
            
            # Target path (relative to export root)
            target_rel = os.path.relpath(
                item['target_path'], 
                os.path.dirname(item['target_path']).split(os.sep)[0]
            )
            self.preview_table.setItem(row, 1, QTableWidgetItem(target_rel))
            
            # File size
            size_mb = item['file_size'] / (1024 * 1024)
            size_item = QTableWidgetItem(f"{size_mb:.1f} MB")
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.preview_table.setItem(row, 2, size_item)
            
            # Status
            status_item = QTableWidgetItem(item['status'])
            if item['status'] == "File exists":
                status_item.setBackground(Qt.yellow)
            elif item['status'] == "Error":
                status_item.setBackground(Qt.red)
            
            self.preview_table.setItem(row, 3, status_item)
    
    def _execute_export(self):
        """Execute the export operation."""
        if not self.export_plan:
            QMessageBox.warning(self, "No Preview", "Please generate a preview first")
            return
        
        # Confirm export
        operation = self.operation_combo.currentText()
        file_count = len(self.export_plan)
        
        reply = QMessageBox.question(
            self, "Confirm Export",
            f"{operation.title()} {file_count} files?\n\nThis operation cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Start export worker
        self.export_worker = ExportWorker(self.export_plan, operation)
        self.export_worker.progress_updated.connect(self._update_export_progress)
        self.export_worker.export_completed.connect(self._export_finished)
        
        # Show progress dialog
        self.progress_dialog = QProgressDialog(
            "Preparing export...", "Cancel", 0, 100, self
        )
        self.progress_dialog.setWindowTitle("Exporting Images")
        self.progress_dialog.setModal(True)
        self.progress_dialog.canceled.connect(self._cancel_export)
        
        # Disable buttons during export
        self.preview_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        
        # Start export
        self.export_worker.start()
        self.progress_dialog.show()
    
    def _update_export_progress(self, percentage: int, current_file: str):
        """Update export progress."""
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.setValue(percentage)
            self.progress_dialog.setLabelText(current_file)
    
    def _export_finished(self, success: bool, message: str):
        """Handle export completion."""
        # Clean up progress dialog
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
        
        # Re-enable buttons
        self.preview_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        
        # Show result
        if success:
            # Export database if requested
            if self.export_db_check.isChecked():
                self._export_subset_database()
            
            QMessageBox.information(self, "Export Complete", message)
            self.accept()
        else:
            QMessageBox.critical(self, "Export Failed", message)
    
    def _cancel_export(self):
        """Cancel the export operation."""
        if self.export_worker:
            self.export_worker.stop()
    
    def _export_subset_database(self):
        """Export a subset database with only exported images."""
        try:
            export_path = self.export_path_edit.text()
            db_path = os.path.join(export_path, '.photo_manager.db')
            
            # TODO: Implement database subset export
            # This would create a new database with only the exported images
            
        except Exception as e:
            QMessageBox.warning(self, "Database Export Error", 
                              f"Failed to export database: {e}")


class QueryBuilderDialog(QDialog):
    """Dialog for building complex queries with a visual interface."""
    
    def __init__(self, tag_manager, parent=None):
        super().__init__(parent)
        
        self.tag_manager = tag_manager
        self.available_tags = {}
        
        self._init_ui()
        self._load_available_tags()
    
    def _init_ui(self):
        """Initialize the query builder dialog."""
        self.setWindowTitle("Query Builder")
        self.setModal(True)
        self.resize(600, 500)
        
        layout = QVBoxLayout(self)
        
        # Query construction area
        query_group = QGroupBox("Build Query")
        query_layout = QVBoxLayout(query_group)
        
        # Tag selection
        tag_layout = QHBoxLayout()
        
        self.category_combo = QComboBox()
        self.category_combo.currentTextChanged.connect(self._update_tag_list)
        
        self.tag_combo = QComboBox()
        
        self.operator_combo = QComboBox()
        self.operator_combo.addItems(["AND", "OR", "NOT"])
        
        add_condition_btn = QPushButton("Add Condition")
        add_condition_btn.clicked.connect(self._add_condition)
        
        tag_layout.addWidget(QLabel("Category:"))
        tag_layout.addWidget(self.category_combo)
        tag_layout.addWidget(QLabel("Tag:"))
        tag_layout.addWidget(self.tag_combo)
        tag_layout.addWidget(QLabel("Operator:"))
        tag_layout.addWidget(self.operator_combo)
        tag_layout.addWidget(add_condition_btn)
        
        query_layout.addLayout(tag_layout)
        
        # Current query display
        self.query_text = QTextEdit()
        self.query_text.setMaximumHeight(100)
        query_layout.addWidget(QLabel("Current Query:"))
        query_layout.addWidget(self.query_text)
        
        # Clear and test buttons
        button_layout = QHBoxLayout()
        clear_btn = QPushButton("Clear Query")
        clear_btn.clicked.connect(self._clear_query)
        
        test_btn = QPushButton("Test Query")
        test_btn.clicked.connect(self._test_query)
        
        button_layout.addWidget(clear_btn)
        button_layout.addWidget(test_btn)
        button_layout.addStretch()
        
        query_layout.addLayout(button_layout)
        layout.addWidget(query_group)
        
        # Results preview
        results_group = QGroupBox("Results Preview")
        results_layout = QVBoxLayout(results_group)
        
        self.results_list = QListWidget()
        self.results_list.setMaximumHeight(150)
        results_layout.addWidget(self.results_list)
        
        self.results_summary = QLabel("No query executed")
        results_layout.addWidget(self.results_summary)
        
        layout.addWidget(results_group)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _load_available_tags(self):
        """Load available tags from database."""
        if not self.tag_manager:
            return
        
        try:
            # TODO: Get actual tags from database
            self.available_tags = {
                'event_tags': ['birthday', 'vacation', 'holiday'],
                'people_tags': ['child1', 'child2', 'family'],
                'scene_tags': ['outdoor', 'indoor', 'landscape'],
                'favorites': ['true', 'false'],
                'to_delete': ['true', 'false']
            }
            
            self.category_combo.addItems(list(self.available_tags.keys()))
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load tags: {e}")
    
    def _update_tag_list(self, category: str):
        """Update tag list based on selected category."""
        self.tag_combo.clear()
        if category in self.available_tags:
            self.tag_combo.addItems(self.available_tags[category])
    
    def _add_condition(self):
        """Add condition to the query."""
        category = self.category_combo.currentText()
        tag = self.tag_combo.currentText()
        operator = self.operator_combo.currentText()
        
        if not category or not tag:
            return
        
        current_query = self.query_text.toPlainText().strip()
        new_condition = f"{category}:{tag}"
        
        if current_query:
            new_query = f"{current_query} {operator} {new_condition}"
        else:
            new_query = new_condition
        
        self.query_text.setPlainText(new_query)
    
    def _clear_query(self):
        """Clear the current query."""
        self.query_text.clear()
        self.results_list.clear()
        self.results_summary.setText("No query executed")
    
    def _test_query(self):
        """Test the current query."""
        query = self.query_text.toPlainText().strip()
        if not query:
            return
        
        try:
            # TODO: Execute actual query
            # Mock results for now
            results = [
                {'filename': 'birthday001.jpg', 'file_path': '/photos/birthday001.jpg'},
                {'filename': 'birthday002.jpg', 'file_path': '/photos/birthday002.jpg'}
            ]
            
            self.results_list.clear()
            for result in results:
                self.results_list.addItem(result['filename'])
            
            self.results_summary.setText(f"Query returned {len(results)} images")
            
        except Exception as e:
            QMessageBox.critical(self, "Query Error", f"Query failed: {e}")
            self.results_summary.setText(f"Query error: {e}")
    
    def get_query(self) -> str:
        """Get the constructed query."""
        return self.query_text.toPlainText().strip()


class DatabaseMaintenanceDialog(QDialog):
    """Dialog for database maintenance operations."""
    
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        
        self.db_manager = db_manager
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the maintenance dialog."""
        self.setWindowTitle("Database Maintenance")
        self.setModal(True)
        self.resize(500, 400)
        
        layout = QVBoxLayout(self)
        
        # Statistics section
        stats_group = QGroupBox("Database Statistics")
        stats_layout = QVBoxLayout(stats_group)
        
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setMaximumHeight(150)
        stats_layout.addWidget(self.stats_text)
        
        refresh_stats_btn = QPushButton("Refresh Statistics")
        refresh_stats_btn.clicked.connect(self._refresh_statistics)
        stats_layout.addWidget(refresh_stats_btn)
        
        layout.addWidget(stats_group)
        
        # Maintenance operations
        maintenance_group = QGroupBox("Maintenance Operations")
        maintenance_layout = QVBoxLayout(maintenance_group)
        
        # Clean missing files
        clean_btn = QPushButton("Clean Missing Files")
        clean_btn.clicked.connect(self._clean_missing_files)
        clean_btn.setToolTip("Remove database entries for files that no longer exist")
        maintenance_layout.addWidget(clean_btn)
        
        # Optimize database
        optimize_btn = QPushButton("Optimize Database")
        optimize_btn.clicked.connect(self._optimize_database)
        optimize_btn.setToolTip("Vacuum and optimize database performance")
        maintenance_layout.addWidget(optimize_btn)
        
        # Rebuild thumbnails
        rebuild_btn = QPushButton("Rebuild Thumbnails")
        rebuild_btn.clicked.connect(self._rebuild_thumbnails)
        rebuild_btn.setToolTip("Regenerate thumbnails for all images")
        maintenance_layout.addWidget(rebuild_btn)
        
        # Recalculate hashes
        rehash_btn = QPushButton("Recalculate Hashes")
        rehash_btn.clicked.connect(self._recalculate_hashes)
        rehash_btn.setToolTip("Recalculate perceptual hashes for duplicate detection")
        maintenance_layout.addWidget(rehash_btn)
        
        layout.addWidget(maintenance_group)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        # Load initial statistics
        self._refresh_statistics()
    
    def _refresh_statistics(self):
        """Refresh database statistics."""
        try:
            # TODO: Get actual statistics from database
            stats = {
                'total_images': 1234,
                'total_tags': 567,
                'corrupt_images': 15,
                'missing_files': 8,
                'db_size_mb': 2.5,
                'duplicate_groups': 12
            }
            
            stats_text = f"""Database Statistics:

Images:
• Total Images: {stats['total_images']:,}
• Corrupt Images: {stats['corrupt_images']}
• Missing Files: {stats['missing_files']}

Tags:
• Total Tags Applied: {stats['total_tags']:,}
• Unique Tag Names: {len(set())}  # TODO: Calculate unique tags

Duplicates:
• Potential Duplicate Groups: {stats['duplicate_groups']}

Storage:
• Database Size: {stats['db_size_mb']:.1f} MB
• Last Optimized: Never  # TODO: Track optimization
"""
            
            self.stats_text.setText(stats_text)
            
        except Exception as e:
            self.stats_text.setText(f"Error loading statistics: {e}")
    
    def _clean_missing_files(self):
        """Clean missing files from database."""
        reply = QMessageBox.question(
            self, "Confirm Cleanup",
            "Remove database entries for missing files?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # TODO: Implement missing file cleanup
                QMessageBox.information(self, "Cleanup", "Missing file cleanup not yet implemented")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Cleanup failed: {e}")
    
    def _optimize_database(self):
        """Optimize database performance."""
        try:
            # TODO: Implement database optimization
            QMessageBox.information(self, "Optimize", "Database optimization not yet implemented")
            self._refresh_statistics()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Optimization failed: {e}")
    
    def _rebuild_thumbnails(self):
        """Rebuild all thumbnails."""
        reply = QMessageBox.question(
            self, "Confirm Rebuild",
            "Rebuild all thumbnails?\n\nThis may take a while for large collections.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # TODO: Implement thumbnail rebuilding
                QMessageBox.information(self, "Rebuild", "Thumbnail rebuild not yet implemented")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Rebuild failed: {e}")
    
    def _recalculate_hashes(self):
        """Recalculate perceptual hashes."""
        reply = QMessageBox.question(
            self, "Confirm Recalculation",
            "Recalculate all image hashes?\n\nThis may take a while for large collections.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # TODO: Implement hash recalculation
                QMessageBox.information(self, "Recalculate", "Hash recalculation not yet implemented")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Recalculation failed: {e}")


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
    dialog = ExportPreviewDialog(db_manager, tag_manager, current_directory, parent)
    result = dialog.exec()
    return result == QDialog.Accepted


def show_query_builder(tag_manager, parent=None) -> Optional[str]:
    """
    Show query builder dialog.
    
    Returns:
        str: Built query string, or None if cancelled
    """
    dialog = QueryBuilderDialog(tag_manager, parent)
    if dialog.exec() == QDialog.Accepted:
        return dialog.get_query()
    return None


def show_database_maintenance(db_manager, parent=None):
    """Show database maintenance dialog."""
    dialog = DatabaseMaintenanceDialog(db_manager, parent)
    dialog.exec()