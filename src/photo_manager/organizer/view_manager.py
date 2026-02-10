"""Manages switching between grid and single-image views."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QStackedWidget, QVBoxLayout

from photo_manager.config.config import ConfigManager
from photo_manager.organizer.grid_view import GridView
from photo_manager.organizer.image_source import ImageSource
from photo_manager.organizer.single_image_view import SingleImageView
from photo_manager.organizer.thumbnail_worker import ThumbnailWorker


class ViewMode:
    GRID = "grid"
    SINGLE = "single"


class ViewManager(QWidget):
    """Stacked widget switching between grid and single-image views."""

    view_changed = pyqtSignal(str)  # "grid" or "single"

    def __init__(
        self,
        image_source: ImageSource,
        config: ConfigManager | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._config = config or ConfigManager()
        self._source = image_source
        self._mode = ViewMode.GRID

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Thumbnail worker
        thumb_size_cfg = self._config.get("performance.thumbnail_size", [256, 256])
        thumb_size = (thumb_size_cfg[0], thumb_size_cfg[1])
        cache_count = self._config.get("organizer.thumbnail_cache_count", 500)
        self._thumb_worker = ThumbnailWorker(
            thumb_size=thumb_size,
            cache_count=cache_count,
        )

        # Grid view
        columns = self._config.get("organizer.grid_columns", 5)
        self._grid = GridView(
            self._thumb_worker,
            columns=columns,
            thumb_size=thumb_size[0],
        )
        self._grid.image_activated.connect(self.show_single)
        self._stack.addWidget(self._grid)

        # Single image view
        self._single = SingleImageView(config=self._config)
        self._single.current_index_changed.connect(self._on_single_index_changed)
        self._stack.addWidget(self._single)

        # Connect image source changes
        self._source.images_changed.connect(self._refresh_views)

        # Initial populate
        self._refresh_views()

        # Start in configured default view
        default_view = self._config.get("organizer.default_view", "grid")
        if default_view == "single":
            self.show_single(0)
        else:
            self.show_grid()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def grid_view(self) -> GridView:
        return self._grid

    @property
    def single_view(self) -> SingleImageView:
        return self._single

    def toggle_view(self) -> None:
        if self._mode == ViewMode.GRID:
            selected = self._grid.get_selected_indices()
            idx = selected[0] if selected else 0
            self.show_single(idx)
        else:
            self.show_grid()

    def show_single(self, index: int = 0) -> None:
        self._mode = ViewMode.SINGLE
        file_list = self._source.get_file_list()
        if file_list:
            self._single.set_images(file_list, start_index=index)
        self._stack.setCurrentWidget(self._single)
        self._single.setFocus()
        self.view_changed.emit(ViewMode.SINGLE)

    def show_grid(self) -> None:
        self._mode = ViewMode.GRID
        # Highlight the image we were viewing in single view
        current_idx = self._single.current_index
        self._stack.setCurrentWidget(self._grid)
        self._grid.select_index(current_idx)
        self._grid.setFocus()
        self.view_changed.emit(ViewMode.GRID)

    def shutdown(self) -> None:
        self._single.shutdown()
        self._thumb_worker.shutdown()

    def _refresh_views(self) -> None:
        file_list = self._source.get_file_list()
        filenames = [Path(f).name for f in file_list]
        self._grid.set_images(file_list, filenames)
        # Also refresh the single view if it's active
        if self._mode == ViewMode.SINGLE:
            current = self._single.current_index
            # Clamp index to new list bounds
            if file_list:
                idx = min(current, len(file_list) - 1)
                self._single.set_images(file_list, start_index=max(0, idx))
            else:
                self._single.set_images([], start_index=0)

    def _on_single_index_changed(self, index: int) -> None:
        """Keep grid selection in sync when navigating in single view."""
        pass  # Grid will sync when we switch back
