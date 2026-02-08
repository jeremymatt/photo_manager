"""Thumbnail grid view for browsing images."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint
from PyQt6.QtGui import QPixmap, QColor, QPainter, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QMenu,
    QScrollArea,
    QWidget,
    QVBoxLayout,
    QLabel,
    QFrame,
    QSizePolicy,
)

from photo_manager.organizer.thumbnail_worker import ThumbnailWorker


class ThumbnailCell(QFrame):
    """A single thumbnail cell in the grid."""

    clicked = pyqtSignal(int)
    double_clicked = pyqtSignal(int)

    def __init__(self, index: int, thumb_size: int, parent=None):
        super().__init__(parent)
        self._index = index
        self._selected = False
        self._thumb_size = thumb_size

        self.setFixedSize(thumb_size + 16, thumb_size + 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._image_label = QLabel()
        self._image_label.setFixedSize(thumb_size, thumb_size)
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

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        scaled = pixmap.scaled(
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
        self._columns = max(1, cols)
        self._layout_cells()

    def set_thumb_size(self, size: int) -> None:
        self._thumb_size = size

    def set_cells(self, cells: list[ThumbnailCell]) -> None:
        self._cells = cells
        for cell in cells:
            cell.setParent(self)
        self._layout_cells()

    def _layout_cells(self) -> None:
        cell_w = self._thumb_size + 16
        cell_h = self._thumb_size + 36
        spacing = 6

        for i, cell in enumerate(self._cells):
            row = i // self._columns
            col = i % self._columns
            x = col * (cell_w + spacing) + spacing
            y = row * (cell_h + spacing) + spacing
            cell.move(x, y)
            cell.show()

        # Set total size
        if self._cells:
            rows = (len(self._cells) + self._columns - 1) // self._columns
            total_w = self._columns * (cell_w + spacing) + spacing
            total_h = rows * (cell_h + spacing) + spacing
            self.setMinimumSize(total_w, total_h)
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
        self._last_clicked: int = -1

        # Setup scroll area
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.setStyleSheet("background-color: #111111;")

        self._container = _GridContainer()
        self._container.set_columns(columns)
        self._container.set_thumb_size(thumb_size)
        self.setWidget(self._container)

        # Connect thumbnail worker
        self._thumb_worker.thumbnail_ready.connect(self._on_thumbnail_ready)

    def set_images(self, file_list: list[str], filenames: list[str]) -> None:
        """Populate the grid with images."""
        self._file_list = file_list
        self._selected_indices.clear()
        self._last_clicked = -1

        # Create cells
        self._cells = []
        for i, (fp, fn) in enumerate(zip(file_list, filenames)):
            cell = ThumbnailCell(i, self._thumb_size)
            cell.set_filename(fn)
            cell.clicked.connect(self._on_cell_clicked)
            cell.double_clicked.connect(self._on_cell_double_clicked)
            self._cells.append(cell)

        self._container.set_cells(self._cells)
        self._request_visible_thumbnails()

    def set_columns(self, columns: int) -> None:
        self._columns = columns
        self._container.set_columns(columns)

    def select_index(self, index: int) -> None:
        """Select a single cell and scroll to it."""
        self._clear_selection()
        if 0 <= index < len(self._cells):
            self._selected_indices.add(index)
            self._cells[index].selected = True
            self._last_clicked = index
            self.ensureWidgetVisible(self._cells[index])
        self.selection_changed.emit(list(self._selected_indices))

    def get_selected_indices(self) -> list[int]:
        return sorted(self._selected_indices)

    def _clear_selection(self) -> None:
        for idx in self._selected_indices:
            if 0 <= idx < len(self._cells):
                self._cells[idx].selected = False
        self._selected_indices.clear()

    def _on_cell_clicked(self, index: int) -> None:
        from PyQt6.QtWidgets import QApplication

        modifiers = QApplication.keyboardModifiers()

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            # Toggle selection
            if index in self._selected_indices:
                self._selected_indices.discard(index)
                self._cells[index].selected = False
            else:
                self._selected_indices.add(index)
                self._cells[index].selected = True
        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            # Range selection
            if self._last_clicked >= 0:
                start = min(self._last_clicked, index)
                end = max(self._last_clicked, index)
                for i in range(start, end + 1):
                    self._selected_indices.add(i)
                    self._cells[i].selected = True
        else:
            # Single selection
            self._clear_selection()
            self._selected_indices.add(index)
            self._cells[index].selected = True

        self._last_clicked = index
        self.selection_changed.emit(list(self._selected_indices))

    def _on_cell_double_clicked(self, index: int) -> None:
        self.image_activated.emit(index)

    def _on_thumbnail_ready(self, index: int, pixmap: QPixmap) -> None:
        if 0 <= index < len(self._cells):
            self._cells[index].set_thumbnail(pixmap)

    def _request_visible_thumbnails(self) -> None:
        """Request thumbnails for all cells (visible ones first)."""
        for i, filepath in enumerate(self._file_list):
            self._thumb_worker.request(i, filepath)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        # Could optimize to only request visible thumbnails here

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Arrow key navigation in grid."""
        if not self._cells:
            super().keyPressEvent(event)
            return

        current = self._last_clicked if self._last_clicked >= 0 else 0
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
                    self._selected_indices.add(cell.index)
                    cell.selected = True
                    self._last_clicked = cell.index
                    self.selection_changed.emit(list(self._selected_indices))
                break
        else:
            return  # Clicked on empty space

        menu = QMenu(self)
        edit_tags = menu.addAction("Edit Tags (F2)")
        edit_tags.triggered.connect(self.context_menu_requested.emit)
        menu.exec(event.globalPos())
