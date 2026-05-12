"""Thumbnail grid view for browsing images."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QColor, QPainter, QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import (
    QMenu,
    QScrollArea,
    QWidget,
    QVBoxLayout,
    QLabel,
    QFrame,
)

from photo_manager.organizer.thumbnail_worker import ThumbnailWorker


_CELL_PADDING_W = 16
_CELL_PADDING_H = 36
_CELL_SPACING = 6


class _ThumbnailLabel(QLabel):
    """QLabel that paints overlays (red X, corner label, DUP/KEEP) on top of its pixmap.

    Overlays must be drawn here rather than in the parent QFrame's paintEvent
    because Qt composites child widgets ON TOP of the parent's paint output,
    which would hide anything the parent draws over the image area.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dup_label: str = ""
        self._marked_delete: bool = False
        self._corner_label: str = ""

    def set_dup_label(self, label: str) -> None:
        if label == self._dup_label:
            return
        self._dup_label = label
        self.update()

    def set_marked_delete(self, value: bool) -> None:
        if value == self._marked_delete:
            return
        self._marked_delete = value
        self.update()

    def set_corner_label(self, text: str) -> None:
        if text == self._corner_label:
            return
        self._corner_label = text
        self.update()

    def paintEvent(self, event) -> None:
        # Draw the pixmap (or empty background) first.
        super().paintEvent(event)

        from PyQt6.QtGui import QFont, QFontMetrics

        w = self.width()
        h = self.height()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Red X first so labels sit on top of it (otherwise the X would
        # cross the corner label and obscure dimensions/size text).
        if self._marked_delete:
            pen = QPen(QColor(255, 40, 40, 230))
            pen.setWidth(max(4, w // 50))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(0, 0, w, h)
            painter.drawLine(w, 0, 0, h)

        # Top-left corner label (e.g., "WxH | size")
        if self._corner_label:
            font = QFont("Consolas", 9)
            painter.setFont(font)
            fm = QFontMetrics(font)
            text_w = fm.horizontalAdvance(self._corner_label)
            text_h = fm.height()
            pad_x = 4
            pad_y = 2
            bg_w = text_w + pad_x * 2
            bg_h = text_h + pad_y * 2
            painter.fillRect(0, 0, bg_w, bg_h, QColor(0, 0, 0, 200))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(pad_x, pad_y + fm.ascent(), self._corner_label)

        # Bottom-right KEEP marker (only shown when explicitly set; "DUP"
        # is suppressed since every cell in dup view is a duplicate).
        if self._dup_label:
            font = QFont("Consolas", 11, QFont.Weight.Bold)
            painter.setFont(font)
            fm = QFontMetrics(font)
            text_w = fm.horizontalAdvance(self._dup_label)
            text_h = fm.height()
            pad = 4
            bg_x = w - text_w - pad * 2
            bg_y = h - text_h - pad
            painter.fillRect(
                bg_x, bg_y,
                text_w + pad * 2, text_h + pad // 2,
                QColor(0, 0, 0, 200),
            )
            if self._dup_label == "KEEP":
                painter.setPen(QColor(100, 255, 100))
            else:
                painter.setPen(QColor(220, 220, 220))
            painter.drawText(bg_x + pad, bg_y + fm.ascent(), self._dup_label)

        painter.end()


class ThumbnailCell(QFrame):
    """A single thumbnail cell in the grid."""

    clicked = pyqtSignal(int)
    double_clicked = pyqtSignal(int)

    def __init__(self, index: int, thumb_size: int, parent=None):
        super().__init__(parent)
        self._index = index
        self._selected = False
        self._thumb_size = thumb_size
        self._source_pixmap: QPixmap | None = None

        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._image_label = _ThumbnailLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background-color: #1a1a1a;")
        layout.addWidget(self._image_label)

        self._name_label = QLabel()
        self._name_label.setFixedHeight(20)
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setStyleSheet(
            "color: #cccccc; font-size: 10px;"
        )
        layout.addWidget(self._name_label)

        self._apply_size()
        self._update_style()

    @property
    def index(self) -> int:
        return self._index

    @property
    def selected(self) -> bool:
        return self._selected

    @selected.setter
    def selected(self, value: bool) -> None:
        self._selected = value
        self._update_style()

    def set_thumb_size(self, thumb_size: int) -> None:
        self._thumb_size = thumb_size
        self._apply_size()
        if self._source_pixmap is not None:
            self._render_pixmap()

    def _apply_size(self) -> None:
        self.setFixedSize(
            self._thumb_size + _CELL_PADDING_W,
            self._thumb_size + _CELL_PADDING_H,
        )
        self._image_label.setFixedSize(self._thumb_size, self._thumb_size)

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        self._source_pixmap = pixmap
        self._render_pixmap()

    def _render_pixmap(self) -> None:
        if self._source_pixmap is None:
            return
        scaled = self._source_pixmap.scaled(
            self._thumb_size, self._thumb_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)

    def set_filename(self, name: str) -> None:
        # Truncate long names
        if len(name) > 20:
            name = name[:17] + "..."
        self._name_label.setText(name)

    def set_dup_label(self, label: str) -> None:
        self._image_label.set_dup_label(label)

    def set_marked_delete(self, value: bool) -> None:
        self._image_label.set_marked_delete(value)

    def set_corner_label(self, text: str) -> None:
        self._image_label.set_corner_label(text)

    def _update_style(self) -> None:
        if self._selected:
            self.setStyleSheet(
                "ThumbnailCell { border: 2px solid #4488ff; "
                "background-color: #2a2a3a; }"
            )
        else:
            self.setStyleSheet(
                "ThumbnailCell { border: 1px solid #333333; "
                "background-color: #1e1e1e; }"
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit(self._index)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.double_clicked.emit(self._index)


class _GridContainer(QWidget):
    """Inner widget that holds the grid of thumbnail cells."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cells: list[ThumbnailCell] = []
        self._columns = 5
        self._thumb_size = 200

    def set_columns(self, cols: int) -> None:
        cols = max(1, cols)
        if cols == self._columns:
            return
        self._columns = cols
        self._layout_cells()

    def set_thumb_size(self, size: int) -> None:
        self._thumb_size = size
        self._layout_cells()

    def set_cells(self, cells: list[ThumbnailCell]) -> None:
        # Remove old cells to prevent stale widgets from remaining
        # visible and clickable with out-of-range indices
        for old_cell in self._cells:
            old_cell.hide()
            old_cell.setParent(None)
            old_cell.deleteLater()
        self._cells = cells
        for cell in cells:
            cell.setParent(self)
        self._layout_cells()

    def _layout_cells(self) -> None:
        cell_w = self._thumb_size + _CELL_PADDING_W
        cell_h = self._thumb_size + _CELL_PADDING_H

        for i, cell in enumerate(self._cells):
            row = i // self._columns
            col = i % self._columns
            x = col * (cell_w + _CELL_SPACING) + _CELL_SPACING
            y = row * (cell_h + _CELL_SPACING) + _CELL_SPACING
            cell.move(x, y)
            cell.show()

        if self._cells:
            rows = (len(self._cells) + self._columns - 1) // self._columns
            total_w = self._columns * (cell_w + _CELL_SPACING) + _CELL_SPACING
            total_h = rows * (cell_h + _CELL_SPACING) + _CELL_SPACING
            self.setMinimumSize(total_w, total_h)
            self.resize(total_w, total_h)
        else:
            self.setMinimumSize(0, 0)


class GridView(QScrollArea):
    """Scrollable thumbnail grid for browsing images."""

    image_activated = pyqtSignal(int)
    selection_changed = pyqtSignal(list)
    context_menu_requested = pyqtSignal()

    def __init__(
        self,
        thumb_worker: ThumbnailWorker,
        columns: int = 5,
        thumb_size: int = 200,
        parent=None,
    ):
        super().__init__(parent)
        self._thumb_worker = thumb_worker
        self._columns = columns
        self._thumb_size = thumb_size
        self._file_list: list[str] = []
        self._cells: list[ThumbnailCell] = []
        self._selected_indices: set[int] = set()
        self._anchor: int = -1
        self._anchor_selected: bool = True
        # Cursor moves with arrow nav; anchor only moves on click/ctrl-click,
        # so shift+arrow can extend a stable range.
        self._cursor: int = -1

        # Setup scroll area
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.setStyleSheet("background-color: #111111;")

        self._container = _GridContainer()
        self._container.set_thumb_size(thumb_size)
        self._container.set_columns(columns)
        self.setWidget(self._container)

        # Connect thumbnail worker
        self._thumb_worker.thumbnail_ready.connect(self._on_thumbnail_ready)

    def set_images(self, file_list: list[str], filenames: list[str]) -> None:
        """Populate the grid with images."""
        self._file_list = file_list
        self._selected_indices.clear()
        self._anchor = -1
        self._anchor_selected = True
        self._cursor = -1

        # Create cells
        self._cells = []
        for i, (fp, fn) in enumerate(zip(file_list, filenames)):
            cell = ThumbnailCell(i, self._thumb_size)
            cell.set_filename(fn)
            cell.clicked.connect(self._on_cell_clicked)
            cell.double_clicked.connect(self._on_cell_double_clicked)
            self._cells.append(cell)

        self._container.set_cells(self._cells)
        self._update_columns_for_width()
        self._request_visible_thumbnails()

    def set_columns(self, columns: int) -> None:
        self._columns = max(1, columns)
        self._container.set_columns(self._columns)

    def set_thumb_size(self, thumb_size: int) -> None:
        """Live-update the thumbnail display size."""
        thumb_size = max(40, int(thumb_size))
        if thumb_size == self._thumb_size:
            return
        self._thumb_size = thumb_size
        for cell in self._cells:
            cell.set_thumb_size(thumb_size)
        self._container.set_thumb_size(thumb_size)
        self._update_columns_for_width()

    def thumb_size(self) -> int:
        return self._thumb_size

    def select_index(self, index: int) -> None:
        """Select a single cell and scroll to it."""
        self._clear_selection()
        if 0 <= index < len(self._cells):
            self._selected_indices.add(index)
            self._cells[index].selected = True
            self._anchor = index
            self._anchor_selected = True
            self._cursor = index
            self.ensureWidgetVisible(self._cells[index])
        self.selection_changed.emit(list(self._selected_indices))

    def select_all(self) -> None:
        """Select every cell currently in the grid."""
        self.select_indices(list(range(len(self._cells))))

    def select_indices(self, indices: list[int]) -> None:
        """Select a specific set of cells, replacing any prior selection."""
        self._clear_selection()
        if not indices:
            self._anchor = -1
            self._anchor_selected = True
            self._cursor = -1
            self.selection_changed.emit([])
            return
        first = -1
        for idx in indices:
            if 0 <= idx < len(self._cells):
                self._selected_indices.add(idx)
                self._cells[idx].selected = True
                if first == -1:
                    first = idx
        self._anchor = first
        self._anchor_selected = True
        self._cursor = first
        self.selection_changed.emit(list(self._selected_indices))

    def get_selected_indices(self) -> list[int]:
        return sorted(self._selected_indices)

    def get_visible_count(self) -> int:
        """Number of cells currently in the grid (not viewport-visible)."""
        return len(self._cells)

    def set_dup_labels(self, labels: dict[int, str]) -> None:
        """Set DUP/KEEP labels on grid cells. labels maps index -> label text."""
        for i, cell in enumerate(self._cells):
            cell.set_dup_label(labels.get(i, ""))

    def set_delete_marks(self, marks: dict[int, bool]) -> None:
        """Show/hide red-X overlay per cell. marks maps index -> bool."""
        for i, cell in enumerate(self._cells):
            cell.set_marked_delete(bool(marks.get(i, False)))

    def set_corner_labels(self, labels: dict[int, str]) -> None:
        """Set top-left corner labels per cell. Pass empty dict to clear all."""
        for i, cell in enumerate(self._cells):
            cell.set_corner_label(labels.get(i, ""))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_columns_for_width()

    def _update_columns_for_width(self) -> None:
        """Recompute column count to fit the viewport width."""
        cell_w = self._thumb_size + _CELL_PADDING_W
        viewport_w = self.viewport().width()
        cols = max(1, (viewport_w - _CELL_SPACING) // (cell_w + _CELL_SPACING))
        if cols != self._columns:
            self._columns = cols
            self._container.set_columns(cols)

    def _clear_selection(self) -> None:
        for idx in self._selected_indices:
            if 0 <= idx < len(self._cells):
                self._cells[idx].selected = False
        self._selected_indices.clear()

    def _set_cell_selected(self, index: int, value: bool) -> None:
        if not (0 <= index < len(self._cells)):
            return
        if value:
            self._selected_indices.add(index)
            self._cells[index].selected = True
        else:
            self._selected_indices.discard(index)
            self._cells[index].selected = False

    def _on_cell_clicked(self, index: int) -> None:
        from PyQt6.QtWidgets import QApplication

        modifiers = QApplication.keyboardModifiers()

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            # Toggle selection; new state becomes the anchor state
            new_state = index not in self._selected_indices
            self._set_cell_selected(index, new_state)
            self._anchor = index
            self._anchor_selected = new_state
            self._cursor = index
        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            # Extend from anchor: apply anchor's state across the range.
            # Anchor itself stays put so further shift+clicks extend from it.
            if self._anchor < 0:
                self._anchor = index
                self._anchor_selected = True
            start = min(self._anchor, index)
            end = max(self._anchor, index)
            for i in range(start, end + 1):
                self._set_cell_selected(i, self._anchor_selected)
            self._cursor = index
        else:
            # Plain click: single-select, becomes the anchor
            self._clear_selection()
            self._set_cell_selected(index, True)
            self._anchor = index
            self._anchor_selected = True
            self._cursor = index

        self.selection_changed.emit(list(self._selected_indices))

    def _on_cell_double_clicked(self, index: int) -> None:
        self.image_activated.emit(index)

    def _on_thumbnail_ready(self, index: int, pixmap: QPixmap) -> None:
        if 0 <= index < len(self._cells):
            self._cells[index].set_thumbnail(pixmap)

    def _request_visible_thumbnails(self) -> None:
        """Request thumbnails for all cells (visible ones first)."""
        for i, filepath in enumerate(self._file_list):
            cached = self._thumb_worker.request(i, filepath)
            if cached is not None and i < len(self._cells):
                self._cells[i].set_thumbnail(cached)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Arrow key navigation; Shift+arrow extends selection."""
        if not self._cells:
            super().keyPressEvent(event)
            return

        modifiers = event.modifiers()

        # Let Ctrl/Alt-modified arrows pass through to the key handler for
        # folder/dup-group nav (Shift alone stays here).
        if modifiers & (Qt.KeyboardModifier.ControlModifier
                        | Qt.KeyboardModifier.AltModifier):
            event.ignore()
            return

        # Cursor follows arrow nav; falls back to anchor or 0 if unset.
        if self._cursor >= 0:
            current = self._cursor
        elif self._anchor >= 0:
            current = self._anchor
        else:
            current = 0
        key = event.key()

        if key == Qt.Key.Key_Right:
            new_idx = min(current + 1, len(self._cells) - 1)
        elif key == Qt.Key.Key_Left:
            new_idx = max(current - 1, 0)
        elif key == Qt.Key.Key_Down:
            new_idx = min(current + self._columns, len(self._cells) - 1)
        elif key == Qt.Key.Key_Up:
            new_idx = max(current - self._columns, 0)
        elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            if current >= 0:
                self.image_activated.emit(current)
            return
        else:
            super().keyPressEvent(event)
            return

        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            # Shift+arrow: extend the selection from the anchor to new_idx
            # using the anchor's state (mirrors shift+click behavior).
            if self._anchor < 0:
                self._anchor = current
                self._anchor_selected = True
            start = min(self._anchor, new_idx)
            end = max(self._anchor, new_idx)
            for i in range(start, end + 1):
                self._set_cell_selected(i, self._anchor_selected)
            self._cursor = new_idx
            if 0 <= new_idx < len(self._cells):
                self.ensureWidgetVisible(self._cells[new_idx])
            self.selection_changed.emit(list(self._selected_indices))
        else:
            # Plain arrow: single-select at new_idx (anchor moves)
            self.select_index(new_idx)

    def contextMenuEvent(self, event) -> None:
        """Show right-click context menu."""
        # Find which cell was clicked
        pos = self._container.mapFrom(self, event.pos())
        for cell in self._cells:
            if cell.geometry().contains(pos):
                # If the clicked cell isn't selected, select it
                if cell.index not in self._selected_indices:
                    self._clear_selection()
                    self._set_cell_selected(cell.index, True)
                    self._anchor = cell.index
                    self._anchor_selected = True
                    self._cursor = cell.index
                    self.selection_changed.emit(list(self._selected_indices))
                break
        else:
            return  # Clicked on empty space

        menu = QMenu(self)
        edit_tags = menu.addAction("Edit Tags (F2)")
        edit_tags.triggered.connect(self.context_menu_requested.emit)
        menu.exec(event.globalPos())
