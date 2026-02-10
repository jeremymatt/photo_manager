"""Tag management dialog for editing image tags and properties."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import ImageRecord


_MULTIPLE_VALUES = "(multiple values)"


class PartialDateTimeWidget(QWidget):
    """Widget with individual spinboxes for year/month/day/hour/minute/second.

    Each component can be left unset (shown as "--"). Unknown date parts
    default to 1, unknown time parts default to 0 when constructing a datetime.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Year: 0 = unset, 1800-2200 valid range
        self._year = QSpinBox()
        self._year.setRange(0, 2200)
        self._year.setSpecialValueText("----")
        self._year.setValue(0)

        # Month: 0 = unset, 1-12 valid
        self._month = QSpinBox()
        self._month.setRange(0, 12)
        self._month.setSpecialValueText("--")
        self._month.setValue(0)

        # Day: 0 = unset, 1-31 valid
        self._day = QSpinBox()
        self._day.setRange(0, 31)
        self._day.setSpecialValueText("--")
        self._day.setValue(0)

        # Hour: -1 = unset, 0-23 valid
        self._hour = QSpinBox()
        self._hour.setRange(-1, 23)
        self._hour.setSpecialValueText("--")
        self._hour.setValue(-1)

        # Minute: -1 = unset, 0-59 valid
        self._minute = QSpinBox()
        self._minute.setRange(-1, 59)
        self._minute.setSpecialValueText("--")
        self._minute.setValue(-1)

        # Second: -1 = unset, 0-59 valid
        self._second = QSpinBox()
        self._second.setRange(-1, 59)
        self._second.setSpecialValueText("--")
        self._second.setValue(-1)

        for label, spin in [
            ("Y:", self._year),
            ("M:", self._month),
            ("D:", self._day),
            ("H:", self._hour),
            ("m:", self._minute),
            ("s:", self._second),
        ]:
            layout.addWidget(QLabel(label))
            layout.addWidget(spin)

    def set_from_record(self, record: ImageRecord) -> None:
        """Populate spinboxes from an ImageRecord's datetime fields."""
        self._year.setValue(record.year if record.year is not None else 0)
        self._month.setValue(record.month if record.month is not None else 0)
        self._day.setValue(record.day if record.day is not None else 0)
        self._hour.setValue(record.hour if record.hour is not None else -1)
        self._minute.setValue(record.minute if record.minute is not None else -1)
        self._second.setValue(record.second if record.second is not None else -1)

    def get_values(self) -> dict:
        """Return dict suitable for ImageRecord.set_partial_datetime()."""
        year = self._year.value() if self._year.value() > 0 else None
        month = self._month.value() if self._month.value() > 0 else None
        day = self._day.value() if self._day.value() > 0 else None
        hour = self._hour.value() if self._hour.value() >= 0 else None
        minute = self._minute.value() if self._minute.value() >= 0 else None
        second = self._second.value() if self._second.value() >= 0 else None
        return {
            "year": year, "month": month, "day": day,
            "hour": hour, "minute": minute, "second": second,
        }

    def has_value(self) -> bool:
        """Return True if at least a year is set."""
        return self._year.value() > 0


class TagDialog(QDialog):
    """Dialog for editing tags and properties on one or more images."""

    def __init__(
        self,
        db: DatabaseManager,
        image_records: list[ImageRecord],
        parent=None,
    ):
        super().__init__(parent)
        self._db = db
        self._records = image_records
        self._multi = len(image_records) > 1

        # Track which fields the user explicitly changed
        self._edited_fields: set[str] = set()

        # Pending tag changes
        self._pending_adds: list[tuple[int, str | None]] = []  # (tag_id, value)
        self._pending_removes: list[tuple[int, str | None]] = []  # (tag_id, value)

        self.setWindowTitle(
            f"Edit Tags — {len(image_records)} image(s)"
            if self._multi
            else f"Edit Tags — {image_records[0].filename}"
        )
        self.setMinimumWidth(550)
        self.setMinimumHeight(500)

        layout = QVBoxLayout(self)

        # --- Fixed Fields ---
        self._setup_fixed_fields(layout)

        # --- Dynamic Tags ---
        self._setup_dynamic_tags(layout)

        # --- Status + Buttons ---
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: gray;")
        layout.addWidget(self._status_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Load current values
        self._load_current_values()

    def _setup_fixed_fields(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox("Image Properties")
        grid = QGridLayout()
        row = 0

        # Boolean checkboxes
        self._chk_favorite = QCheckBox("Favorite")
        self._chk_delete = QCheckBox("To Delete")
        self._chk_reviewed = QCheckBox("Reviewed")

        for chk in (self._chk_favorite, self._chk_delete, self._chk_reviewed):
            if self._multi:
                chk.setTristate(True)
            grid.addWidget(chk, row, 0, 1, 2)
            row += 1

        # DateTime — partial entry with individual spinboxes
        self._chk_apply_datetime = QCheckBox("Apply:")
        self._chk_apply_datetime.setChecked(False)
        self._dt_widget = PartialDateTimeWidget()
        self._dt_widget.setEnabled(False)
        self._chk_apply_datetime.toggled.connect(self._dt_widget.setEnabled)
        grid.addWidget(QLabel("Date/Time:"), row, 0)
        dt_layout = QHBoxLayout()
        dt_layout.addWidget(self._chk_apply_datetime)
        dt_layout.addWidget(self._dt_widget, 1)
        grid.addLayout(dt_layout, row, 1)
        row += 1

        # Location text fields
        self._txt_city = QLineEdit()
        self._txt_town = QLineEdit()
        self._txt_state = QLineEdit()

        for label_text, widget, field_name in [
            ("City:", self._txt_city, "city"),
            ("Town:", self._txt_town, "town"),
            ("State:", self._txt_state, "state"),
        ]:
            grid.addWidget(QLabel(label_text), row, 0)
            widget.textEdited.connect(
                lambda _, fn=field_name: self._edited_fields.add(fn)
            )
            grid.addWidget(widget, row, 1)
            row += 1

        group.setLayout(grid)
        parent_layout.addWidget(group)

    def _setup_dynamic_tags(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox("Tags")
        vbox = QVBoxLayout()

        # Tag tree
        self._tag_tree = QTreeWidget()
        columns = ["Tag Path", "Value"]
        if self._multi:
            columns.append("Status")
        self._tag_tree.setHeaderLabels(columns)
        self._tag_tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._tag_tree.setRootIsDecorated(False)
        self._tag_tree.setSelectionMode(
            QTreeWidget.SelectionMode.ExtendedSelection
        )
        vbox.addWidget(self._tag_tree)

        # Add tag row
        add_layout = QHBoxLayout()
        self._txt_tag_path = QLineEdit()
        self._txt_tag_path.setPlaceholderText("Tag path (e.g. person.Alice)")
        self._txt_tag_value = QLineEdit()
        self._txt_tag_value.setPlaceholderText("Value (optional)")

        # Auto-complete from existing tag definitions
        self._setup_completer()

        self._btn_add = QPushButton("Add")
        self._btn_add.clicked.connect(self._add_tag)
        self._txt_tag_path.returnPressed.connect(self._add_tag)

        add_layout.addWidget(self._txt_tag_path, 2)
        add_layout.addWidget(self._txt_tag_value, 1)
        add_layout.addWidget(self._btn_add)
        vbox.addLayout(add_layout)

        # Remove button
        self._btn_remove = QPushButton("Remove Selected")
        self._btn_remove.clicked.connect(self._remove_selected_tags)
        vbox.addWidget(self._btn_remove)

        group.setLayout(vbox)
        parent_layout.addWidget(group)

    def _setup_completer(self) -> None:
        """Build auto-complete list from all existing tag definitions."""
        all_defs = self._db.get_all_tag_definitions()
        paths = []
        for td in all_defs:
            paths.append(self._db.get_tag_path(td.id))
        completer = QCompleter(sorted(set(paths)))
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._txt_tag_path.setCompleter(completer)

    def _load_current_values(self) -> None:
        """Load current field values and tags from all selected images."""
        records = self._records

        # --- Fixed fields ---
        favs = [r.favorite for r in records]
        dels = [r.to_delete for r in records]
        revs = [r.reviewed for r in records]

        self._set_checkbox(self._chk_favorite, favs)
        self._set_checkbox(self._chk_delete, dels)
        self._set_checkbox(self._chk_reviewed, revs)

        # DateTime — use first record's values for the partial widget
        self._dt_widget.set_from_record(records[0])

        # Location fields
        self._set_text_field(self._txt_city, [r.city for r in records])
        self._set_text_field(self._txt_town, [r.town for r in records])
        self._set_text_field(self._txt_state, [r.state for r in records])

        # --- Dynamic tags ---
        # Build a map of {(tag_path, value): count}
        tag_counts: dict[tuple[str, str | None], int] = {}
        self._tag_id_map: dict[str, int] = {}  # path -> tag_id

        for record in records:
            if record.id is None:
                continue
            image_tags = self._db.get_image_tags(record.id)
            for it in image_tags:
                path = self._db.get_tag_path(it.tag_id)
                self._tag_id_map[path] = it.tag_id
                key = (path, it.value)
                tag_counts[key] = tag_counts.get(key, 0) + 1

        total = len(records)
        for (path, value), count in sorted(tag_counts.items()):
            item = QTreeWidgetItem()
            item.setText(0, path)
            item.setText(1, value or "")
            if self._multi:
                status = "all" if count == total else f"{count}/{total}"
                item.setText(2, status)
            item.setData(0, Qt.ItemDataRole.UserRole, path)
            item.setData(1, Qt.ItemDataRole.UserRole, value)
            self._tag_tree.addTopLevelItem(item)

    def _set_checkbox(self, chk: QCheckBox, values: list[bool]) -> None:
        if all(values):
            chk.setCheckState(Qt.CheckState.Checked)
        elif not any(values):
            chk.setCheckState(Qt.CheckState.Unchecked)
        else:
            chk.setCheckState(Qt.CheckState.PartiallyChecked)

    def _set_text_field(
        self, widget: QLineEdit, values: list[str | None]
    ) -> None:
        unique = set(v or "" for v in values)
        if len(unique) == 1:
            widget.setText(unique.pop())
        else:
            widget.setPlaceholderText(_MULTIPLE_VALUES)

    def _add_tag(self) -> None:
        path = self._txt_tag_path.text().strip()
        if not path:
            self._status_label.setText("Enter a tag path")
            self._status_label.setStyleSheet("color: orange;")
            return

        value = self._txt_tag_value.text().strip() or None

        # Ensure the tag definition exists (creates if needed)
        tag_def = self._db.ensure_tag_path(path)
        self._tag_id_map[path] = tag_def.id
        self._pending_adds.append((tag_def.id, value))

        # Add to tree widget
        item = QTreeWidgetItem()
        item.setText(0, path)
        item.setText(1, value or "")
        if self._multi:
            item.setText(2, "pending")
        item.setData(0, Qt.ItemDataRole.UserRole, path)
        item.setData(1, Qt.ItemDataRole.UserRole, value)
        self._tag_tree.addTopLevelItem(item)

        # Clear inputs
        self._txt_tag_path.clear()
        self._txt_tag_value.clear()
        self._status_label.setText(f"Added: {path}")
        self._status_label.setStyleSheet("color: green;")

        # Refresh completer to include newly created paths
        self._setup_completer()

    def _remove_selected_tags(self) -> None:
        selected = self._tag_tree.selectedItems()
        if not selected:
            self._status_label.setText("Select tags to remove")
            self._status_label.setStyleSheet("color: orange;")
            return

        for item in selected:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            value = item.data(1, Qt.ItemDataRole.UserRole)
            tag_id = self._tag_id_map.get(path)
            if tag_id is not None:
                self._pending_removes.append((tag_id, value))
            idx = self._tag_tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self._tag_tree.takeTopLevelItem(idx)

        self._status_label.setText(f"Removed {len(selected)} tag(s)")
        self._status_label.setStyleSheet("color: green;")

    def _accept(self) -> None:
        """Apply all changes to all selected images."""
        for record in self._records:
            if record.id is None:
                continue

            # --- Fixed fields ---
            # Booleans: only apply if not PartiallyChecked
            fav_state = self._chk_favorite.checkState()
            if fav_state != Qt.CheckState.PartiallyChecked:
                record.favorite = fav_state == Qt.CheckState.Checked

            del_state = self._chk_delete.checkState()
            if del_state != Qt.CheckState.PartiallyChecked:
                record.to_delete = del_state == Qt.CheckState.Checked

            rev_state = self._chk_reviewed.checkState()
            if rev_state != Qt.CheckState.PartiallyChecked:
                record.reviewed = rev_state == Qt.CheckState.Checked

            # DateTime: only if "Apply" is checked
            if self._chk_apply_datetime.isChecked():
                record.set_partial_datetime(**self._dt_widget.get_values())

            # Location: only if user edited the field
            if "city" in self._edited_fields:
                record.city = self._txt_city.text().strip() or None
            if "town" in self._edited_fields:
                record.town = self._txt_town.text().strip() or None
            if "state" in self._edited_fields:
                record.state = self._txt_state.text().strip() or None

            self._db.update_image(record)

            # --- Dynamic tags ---
            for tag_id, value in self._pending_adds:
                self._db.set_image_tag(record.id, tag_id, value)

            for tag_id, value in self._pending_removes:
                self._db.remove_image_tag(record.id, tag_id, value)

        self.accept()
