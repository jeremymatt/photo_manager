"""Create or open database dialog."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)


class DatabaseDialog(QDialog):
    """Dialog to create a new database or open an existing one."""

    def __init__(self, parent=None, last_db_path: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Photo Manager - Database")
        self.setMinimumWidth(500)

        self._db_path: str | None = None
        self._is_new: bool = False

        layout = QVBoxLayout(self)

        # Mode selection
        self._radio_create = QRadioButton("Create new database")
        self._radio_open = QRadioButton("Open existing database")
        self._radio_create.setChecked(True)
        layout.addWidget(self._radio_create)
        layout.addWidget(self._radio_open)

        # Path picker
        path_layout = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Database file path...")
        if last_db_path:
            self._path_edit.setText(last_db_path)
            self._radio_open.setChecked(True)
        self._browse_btn = QPushButton("Browse...")
        self._browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(self._path_edit)
        path_layout.addWidget(self._browse_btn)
        layout.addLayout(path_layout)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: gray;")
        layout.addWidget(self._status_label)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Connect signals
        self._radio_create.toggled.connect(self._update_status)
        self._radio_open.toggled.connect(self._update_status)
        self._path_edit.textChanged.connect(self._update_status)

    @property
    def db_path(self) -> str | None:
        return self._db_path

    @property
    def is_new(self) -> bool:
        return self._is_new

    def _browse(self) -> None:
        if self._radio_create.isChecked():
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Create Database",
                "",
                "Database files (*.db);;All files (*)",
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Open Database",
                "",
                "Database files (*.db);;All files (*)",
            )
        if path:
            self._path_edit.setText(path)

    def _update_status(self) -> None:
        path = self._path_edit.text().strip()
        if not path:
            self._status_label.setText("")
            return

        p = Path(path)
        if self._radio_open.isChecked():
            if p.exists():
                self._status_label.setText("Database found")
                self._status_label.setStyleSheet("color: green;")
            else:
                self._status_label.setText("File not found")
                self._status_label.setStyleSheet("color: red;")
        else:
            if p.exists():
                self._status_label.setText("File already exists (will be overwritten)")
                self._status_label.setStyleSheet("color: orange;")
            else:
                self._status_label.setText("Will create new database")
                self._status_label.setStyleSheet("color: green;")

    def _accept(self) -> None:
        path = self._path_edit.text().strip()
        if not path:
            self._status_label.setText("Please enter a database path")
            self._status_label.setStyleSheet("color: red;")
            return

        p = Path(path)
        if self._radio_open.isChecked() and not p.exists():
            self._status_label.setText("File not found")
            self._status_label.setStyleSheet("color: red;")
            return

        self._db_path = path
        self._is_new = self._radio_create.isChecked()
        self.accept()
