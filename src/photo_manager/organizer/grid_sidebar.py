"""Sidebar widget for the grid view: view selector, thumb-size slider, batch ops."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)


VIEW_ALL = "all"
VIEW_FOLDER = "folder"
VIEW_DUPLICATES = "duplicates"

_VIEW_LABEL_TO_KEY = {
    "All Images": VIEW_ALL,
    "Current Folder": VIEW_FOLDER,
    "Duplicates": VIEW_DUPLICATES,
}
_VIEW_KEY_TO_LABEL = {v: k for k, v in _VIEW_LABEL_TO_KEY.items()}


class GridSidebar(QWidget):
    """Controls for the grid view: view selector, thumb-size slider, batch tag."""

    view_mode_changed = pyqtSignal(str)
    thumb_size_changed = pyqtSignal(int)
    batch_tags_requested = pyqtSignal()

    def __init__(
        self,
        thumb_size: int,
        thumb_size_min: int = 80,
        thumb_size_max: int = 400,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setStyleSheet(
            "GridSidebar { background-color: #1e1e1e; "
            "border-right: 1px solid #333333; }"
            "QLabel { color: #cccccc; }"
            "QPushButton { padding: 6px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # --- View selector ---
        layout.addWidget(self._section_label("View"))
        self._view_combo = QComboBox()
        for label in _VIEW_LABEL_TO_KEY.keys():
            self._view_combo.addItem(label)
        self._view_combo.currentIndexChanged.connect(self._on_view_changed)
        layout.addWidget(self._view_combo)

        # Folder path display (only visible in folder view)
        self._folder_label = QLabel("(no folder)")
        self._folder_label.setWordWrap(False)
        self._folder_label.setStyleSheet(
            "color: #999999; font-size: 10px; padding: 2px;"
        )
        self._folder_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self._folder_label.setVisible(False)
        layout.addWidget(self._folder_label)

        layout.addWidget(self._separator())

        # --- Thumbnail size ---
        layout.addWidget(self._section_label("Thumbnail size"))
        self._size_slider = QSlider(Qt.Orientation.Horizontal)
        self._size_slider.setRange(thumb_size_min, thumb_size_max)
        self._size_slider.setValue(thumb_size)
        self._size_slider.setSingleStep(20)
        self._size_slider.setPageStep(40)
        self._size_value = QLabel(f"{thumb_size} px")
        self._size_value.setStyleSheet("color: #888888; font-size: 10px;")
        self._size_slider.valueChanged.connect(self._on_size_changed)
        layout.addWidget(self._size_slider)
        layout.addWidget(self._size_value)

        layout.addWidget(self._separator())

        # --- Batch tags ---
        layout.addWidget(self._section_label("Batch operations"))
        self._batch_count_label = QLabel("(no images)")
        self._batch_count_label.setStyleSheet(
            "color: #888888; font-size: 10px;"
        )
        layout.addWidget(self._batch_count_label)
        self._batch_tag_btn = QPushButton("Edit Tags…")
        self._batch_tag_btn.clicked.connect(self.batch_tags_requested.emit)
        layout.addWidget(self._batch_tag_btn)

        layout.addStretch(1)

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: #cccccc; font-weight: bold; font-size: 11px;"
        )
        return lbl

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("color: #333333;")
        return line

    # --- public API for ViewManager ---

    def current_view_mode(self) -> str:
        label = self._view_combo.currentText()
        return _VIEW_LABEL_TO_KEY.get(label, VIEW_ALL)

    def set_view_mode(self, mode: str, *, emit: bool = False) -> None:
        """Set the combo selection without (by default) emitting the signal."""
        label = _VIEW_KEY_TO_LABEL.get(mode)
        if label is None:
            return
        idx = self._view_combo.findText(label)
        if idx < 0 or idx == self._view_combo.currentIndex():
            return
        if emit:
            self._view_combo.setCurrentIndex(idx)
        else:
            self._view_combo.blockSignals(True)
            self._view_combo.setCurrentIndex(idx)
            self._view_combo.blockSignals(False)
            self._update_folder_label_visibility()

    def set_folder_path(self, path: str | None) -> None:
        """Update the displayed folder path."""
        if path is None:
            self._folder_label.setText("(no folder)")
            return
        # Elide to fit available width
        fm = QFontMetrics(self._folder_label.font())
        elided = fm.elidedText(
            path, Qt.TextElideMode.ElideMiddle,
            self._folder_label.width() - 8,
        )
        self._folder_label.setText(elided)
        self._folder_label.setToolTip(path)

    def set_batch_counts(self, selected: int, visible: int) -> None:
        """Update the counts shown next to the batch button."""
        if selected > 0:
            self._batch_count_label.setText(
                f"{selected} selected ({visible} visible)"
            )
            self._batch_tag_btn.setEnabled(True)
        elif visible > 0:
            self._batch_count_label.setText(f"{visible} visible (none selected)")
            self._batch_tag_btn.setEnabled(True)
        else:
            self._batch_count_label.setText("(no images)")
            self._batch_tag_btn.setEnabled(False)

    def thumb_size(self) -> int:
        return self._size_slider.value()

    # --- internal handlers ---

    def _on_view_changed(self, _idx: int) -> None:
        self._update_folder_label_visibility()
        self.view_mode_changed.emit(self.current_view_mode())

    def _on_size_changed(self, value: int) -> None:
        self._size_value.setText(f"{value} px")
        self.thumb_size_changed.emit(value)

    def _update_folder_label_visibility(self) -> None:
        self._folder_label.setVisible(
            self.current_view_mode() == VIEW_FOLDER
        )
