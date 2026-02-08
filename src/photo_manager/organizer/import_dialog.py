"""Import directory workflow dialog."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from photo_manager.db.manager import DatabaseManager
from photo_manager.scanner.tag_template import (
    load_template_auto,
    validate_template,
    TagTemplate,
)


class ImportDialog(QDialog):
    """Dialog to configure and start a directory import."""

    def __init__(
        self,
        db: DatabaseManager,
        initial_dir: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Import Directory")
        self.setMinimumWidth(550)

        self._db = db
        self._templates: list[TagTemplate] = []
        self._directory: str | None = None
        self._recursive: bool = True

        layout = QVBoxLayout(self)

        # Directory picker
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Directory:"))
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("Select directory to import...")
        if initial_dir:
            self._dir_edit.setText(initial_dir)
        self._dir_edit.textChanged.connect(self._on_dir_changed)
        dir_layout.addWidget(self._dir_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        dir_layout.addWidget(browse_btn)
        layout.addLayout(dir_layout)

        # Options
        self._recursive_cb = QCheckBox("Scan subdirectories recursively")
        self._recursive_cb.setChecked(True)
        layout.addWidget(self._recursive_cb)

        # Template info
        self._template_group = QGroupBox("Load Template")
        tmpl_layout = QVBoxLayout(self._template_group)
        self._template_label = QLabel("No template detected")
        self._template_label.setStyleSheet("color: gray;")
        tmpl_layout.addWidget(self._template_label)
        self._warnings_text = QTextEdit()
        self._warnings_text.setReadOnly(True)
        self._warnings_text.setMaximumHeight(100)
        self._warnings_text.setVisible(False)
        tmpl_layout.addWidget(self._warnings_text)
        layout.addWidget(self._template_group)

        # Status
        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Import")
        self._ok_btn.setEnabled(False)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Auto-detect template if initial dir provided
        if initial_dir:
            self._on_dir_changed(initial_dir)

    @property
    def directory(self) -> str | None:
        return self._directory

    @property
    def templates(self) -> list[TagTemplate]:
        return self._templates

    @property
    def recursive(self) -> bool:
        return self._recursive_cb.isChecked()

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Directory to Import"
        )
        if path:
            self._dir_edit.setText(path)

    def _on_dir_changed(self, text: str) -> None:
        path = text.strip()
        if not path or not Path(path).is_dir():
            self._ok_btn.setEnabled(False)
            self._template_label.setText("No template detected")
            self._template_label.setStyleSheet("color: gray;")
            self._warnings_text.setVisible(False)
            self._templates = []
            return

        self._ok_btn.setEnabled(True)

        # Auto-detect template
        self._templates = load_template_auto(path)
        if self._templates:
            tmpl = self._templates[0]
            self._template_label.setText(
                f"Template found: {tmpl.raw_template}"
            )
            self._template_label.setStyleSheet("color: green;")

            # Validate against DB
            all_warnings = []
            for t in self._templates:
                all_warnings.extend(validate_template(t, self._db))
            if all_warnings:
                self._warnings_text.setVisible(True)
                self._warnings_text.setPlainText(
                    "\n".join(all_warnings)
                )
            else:
                self._warnings_text.setVisible(False)
        else:
            self._template_label.setText(
                "No load template found (tags will not be auto-populated)"
            )
            self._template_label.setStyleSheet("color: orange;")
            self._warnings_text.setVisible(False)

    def _accept(self) -> None:
        path = self._dir_edit.text().strip()
        if not path or not Path(path).is_dir():
            self._status_label.setText("Invalid directory")
            self._status_label.setStyleSheet("color: red;")
            return
        self._directory = path
        self._recursive = self._recursive_cb.isChecked()
        self.accept()
