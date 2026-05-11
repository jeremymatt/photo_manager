"""Manages switching between grid and single-image views."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QSplitter, QStackedWidget, QVBoxLayout, QWidget

from photo_manager.config.config import ConfigManager
from photo_manager.organizer.grid_sidebar import (
    GridSidebar,
    VIEW_ALL,
    VIEW_DUPLICATES,
    VIEW_FOLDER,
)
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
    batch_tags_requested = pyqtSignal()
    grid_repopulated = pyqtSignal()  # emitted whenever grid cells are rebuilt

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

        # Grid view + sidebar wrapped in a splitter
        columns = self._config.get("organizer.grid_columns", 5)
        initial_grid_thumb = self._config.get(
            "organizer.grid_thumb_size", thumb_size[0]
        )
        self._grid = GridView(
            self._thumb_worker,
            columns=columns,
            thumb_size=initial_grid_thumb,
        )
        self._grid.image_activated.connect(self.show_single)
        self._grid.selection_changed.connect(self._on_grid_selection_changed)

        self._sidebar = GridSidebar(thumb_size=initial_grid_thumb)
        self._sidebar.thumb_size_changed.connect(self._grid.set_thumb_size)
        self._sidebar.view_mode_changed.connect(self._on_view_mode_changed)
        self._sidebar.batch_tags_requested.connect(self.batch_tags_requested.emit)

        grid_page = QSplitter(Qt.Orientation.Horizontal)
        grid_page.addWidget(self._sidebar)
        grid_page.addWidget(self._grid)
        grid_page.setCollapsible(0, True)
        grid_page.setCollapsible(1, False)
        grid_page.setStretchFactor(0, 0)
        grid_page.setStretchFactor(1, 1)
        self._grid_page = grid_page
        self._stack.addWidget(grid_page)

        # Single image view
        self._single = SingleImageView(config=self._config)
        self._single.current_index_changed.connect(self._on_single_index_changed)
        self._stack.addWidget(self._single)

        # Connect image source changes
        self._source.images_changed.connect(self._refresh_views)

        # Initial populate
        self._refresh_views()
        self._refresh_sidebar_counts()

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

    @property
    def sidebar(self) -> GridSidebar:
        return self._sidebar

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
        self._stack.setCurrentWidget(self._grid_page)
        self._grid.select_index(current_idx)
        self._grid.setFocus()
        self.view_changed.emit(ViewMode.GRID)

    def sync_view_mode_to_source(self) -> None:
        """Update the sidebar combo to match the source's current filter state.

        Used when an external action (e.g., F3) toggles the duplicate filter,
        so the sidebar reflects reality.
        """
        if self._source.is_dup_filtered:
            self._sidebar.set_view_mode(VIEW_DUPLICATES)
        elif self._source.folder_filter is not None:
            self._sidebar.set_view_mode(VIEW_FOLDER)
        else:
            self._sidebar.set_view_mode(VIEW_ALL)
        self._refresh_sidebar_folder_label()

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
        self._refresh_sidebar_counts()
        self._refresh_sidebar_folder_label()
        self.grid_repopulated.emit()

    def _on_single_index_changed(self, index: int) -> None:
        """Keep grid selection in sync when navigating in single view."""
        # If we're in folder view, switching the single-view image to one
        # in a different folder should follow.
        if (
            self._mode == ViewMode.SINGLE
            and self._sidebar.current_view_mode() == VIEW_FOLDER
        ):
            new_folder = self._source.folder_for_index(index)
            if new_folder and new_folder != self._source.folder_filter:
                self._source.set_folder_filter(new_folder)

    def _on_grid_selection_changed(self, indices: list) -> None:
        self._refresh_sidebar_counts()

    def _on_view_mode_changed(self, mode: str) -> None:
        if mode == VIEW_DUPLICATES:
            if not self._source.is_dup_filtered:
                self._source.set_folder_filter(None)
                self._source.set_dup_filter(True)
        elif mode == VIEW_FOLDER:
            if self._source.is_dup_filtered:
                self._source.set_dup_filter(False)
            target = self._current_folder_target()
            if target is not None:
                self._source.set_folder_filter(target)
        else:  # VIEW_ALL
            if self._source.is_dup_filtered:
                self._source.set_dup_filter(False)
            if self._source.folder_filter is not None:
                self._source.set_folder_filter(None)
        self._refresh_sidebar_folder_label()

    def _current_folder_target(self) -> str | None:
        """Pick the folder to filter to when entering folder view.

        Prefer the folder of the current single-view image; fall back to
        the first selected grid cell, then the first record.
        """
        idx = self._single.current_index
        folder = self._source.folder_for_index(idx)
        if folder:
            return folder
        selected = self._grid.get_selected_indices()
        if selected:
            return self._source.folder_for_index(selected[0])
        return self._source.folder_for_index(0)

    def _refresh_sidebar_counts(self) -> None:
        selected = len(self._grid.get_selected_indices())
        visible = self._grid.get_visible_count()
        self._sidebar.set_batch_counts(selected, visible)

    def _refresh_sidebar_folder_label(self) -> None:
        self._sidebar.set_folder_path(self._source.folder_filter)
