"""Dialog for editing quick-toggle keybindings at runtime."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from photo_manager.config.config import ConfigManager
from photo_manager.organizer.organizer_key_handler import (
    OrganizerKeyHandler,
    key_tuple_to_string,
    _parse_key_string,
)


class KeyCaptureEdit(QLineEdit):
    """A line edit that captures a key combo when focused."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Click and press a key combo...")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        # Ignore bare modifier keys
        if key in (
            Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            return

        parts = []
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")

        # Convert Qt key to name
        from photo_manager.organizer.organizer_key_handler import _REVERSE_KEY_MAP
        key_name = _REVERSE_KEY_MAP.get(key)
        if key_name is None:
            return
        parts.append(key_name.upper() if len(key_name) == 1 else key_name)
        self.setText("+".join(parts))


class KeybindingDialog(QDialog):
    """Dialog for viewing and editing quick-toggle keybindings."""

    def __init__(
        self,
        config: ConfigManager,
        key_handler: OrganizerKeyHandler,
        parent=None,
    ):
        super().__init__(parent)
        self._config = config
        self._key_handler = key_handler

        self.setWindowTitle("Edit Keybindings")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        # --- Current bindings table ---
        group = QGroupBox("Current Bindings")
        gbox = QVBoxLayout()

        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["Key", "Actions"])
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        gbox.addWidget(self._table)

        # Remove button
        self._btn_remove = QPushButton("Remove Selected")
        self._btn_remove.clicked.connect(self._remove_selected)
        gbox.addWidget(self._btn_remove)

        group.setLayout(gbox)
        layout.addWidget(group)

        # --- Add new binding ---
        add_group = QGroupBox("Add Binding")
        add_layout = QVBoxLayout()

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("Key:"))
        self._key_capture = KeyCaptureEdit()
        key_row.addWidget(self._key_capture, 1)
        add_layout.addLayout(key_row)

        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("Actions:"))
        self._txt_actions = QLineEdit()
        self._txt_actions.setPlaceholderText(
            "e.g. set_reviewed, next_image   or   tag:person.Alice"
        )
        action_row.addWidget(self._txt_actions, 1)
        add_layout.addLayout(action_row)

        self._btn_add = QPushButton("Add Binding")
        self._btn_add.clicked.connect(self._add_binding)
        add_layout.addWidget(self._btn_add)

        self._status = QLabel("")
        self._status.setStyleSheet("color: gray;")
        add_layout.addWidget(self._status)

        add_group.setLayout(add_layout)
        layout.addWidget(add_group)

        # --- OK / Cancel ---
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate_table()

    def _populate_table(self) -> None:
        """Fill the table from config."""
        bindings = self._config.get("organizer.quick_toggle_bindings", {})
        self._table.setRowCount(0)
        if not isinstance(bindings, dict):
            return
        for key_str, actions in bindings.items():
            if isinstance(actions, str):
                actions = [actions]
            if not isinstance(actions, list):
                continue
            row = self._table.rowCount()
            self._table.insertRow(row)
            key_item = QTableWidgetItem(key_str)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, key_item)
            action_item = QTableWidgetItem(", ".join(actions))
            action_item.setFlags(
                action_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            self._table.setItem(row, 1, action_item)

    def _remove_selected(self) -> None:
        rows = sorted(
            set(idx.row() for idx in self._table.selectedIndexes()),
            reverse=True,
        )
        for row in rows:
            self._table.removeRow(row)
        self._status.setText(f"Removed {len(rows)} binding(s)")
        self._status.setStyleSheet("color: green;")

    def _add_binding(self) -> None:
        key_str = self._key_capture.text().strip()
        if not key_str:
            self._status.setText("Press a key combo in the Key field first")
            self._status.setStyleSheet("color: orange;")
            return

        parsed = _parse_key_string(key_str)
        if parsed is None:
            self._status.setText(f"Could not parse key: {key_str}")
            self._status.setStyleSheet("color: red;")
            return

        actions_text = self._txt_actions.text().strip()
        if not actions_text:
            self._status.setText("Enter at least one action")
            self._status.setStyleSheet("color: orange;")
            return

        actions = [a.strip() for a in actions_text.split(",") if a.strip()]

        # Check for duplicate key in the table
        for row in range(self._table.rowCount()):
            existing_key = self._table.item(row, 0).text()
            if _parse_key_string(existing_key) == parsed:
                # Replace the existing row
                self._table.item(row, 1).setText(", ".join(actions))
                self._status.setText(f"Updated: {key_str}")
                self._status.setStyleSheet("color: green;")
                self._key_capture.clear()
                self._txt_actions.clear()
                return

        row = self._table.rowCount()
        self._table.insertRow(row)
        key_item = QTableWidgetItem(key_str)
        key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(row, 0, key_item)
        action_item = QTableWidgetItem(", ".join(actions))
        action_item.setFlags(
            action_item.flags() & ~Qt.ItemFlag.ItemIsEditable
        )
        self._table.setItem(row, 1, action_item)

        self._status.setText(f"Added: {key_str} -> {', '.join(actions)}")
        self._status.setStyleSheet("color: green;")
        self._key_capture.clear()
        self._txt_actions.clear()

    def _accept(self) -> None:
        """Save bindings to config and reload."""
        bindings: dict[str, list[str]] = {}
        for row in range(self._table.rowCount()):
            key_str = self._table.item(row, 0).text()
            actions_str = self._table.item(row, 1).text()
            actions = [a.strip() for a in actions_str.split(",") if a.strip()]
            bindings[key_str] = actions

        self._config.set("organizer.quick_toggle_bindings", bindings)
        self._config.save_session()
        self._key_handler.load_all_bindings(self._config)
        self.accept()
