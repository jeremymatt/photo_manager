"""Single-image view reusing viewer components."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QKeyEvent
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from photo_manager.config.config import ConfigManager
from photo_manager.viewer.gif_player import GifPlayer
from photo_manager.viewer.image_canvas import ImageCanvas
from photo_manager.viewer.image_loader import ImageLoader
from photo_manager.viewer.info_overlay import InfoOverlay


class SingleImageView(QWidget):
    """Full single-image view reusing viewer components."""

    # Emitted when the user navigates to a different image
    current_index_changed = pyqtSignal(int)

    def __init__(
        self,
        config: ConfigManager | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._config = config or ConfigManager()
        self._file_list: list[str] = []
        self._image_loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Canvas
        self._canvas = ImageCanvas(self)
        layout.addWidget(self._canvas)
        self._canvas.set_zoom_limits(
            self._config.get("ui.max_scroll_zoom_percent", 1000),
            self._config.get("ui.max_fit_to_screen_zoom_percent", 250),
        )

        # Image loader (initialized empty, set_images() later)
        self._loader: ImageLoader | None = None

        # GIF player
        self._gif_player = GifPlayer(self)
        self._gif_player.frame_changed.connect(self._on_gif_frame)
        self._is_gif = False

        # Info overlay
        self._info = InfoOverlay(self._canvas)
        info_level = self._config.get("ui.info_display_level", 1)
        while self._info.info_level != info_level:
            self._info.cycle_level()

        # Connect zoom signal
        self._canvas.zoom_changed.connect(lambda _: self._update_info())

    def set_images(self, file_list: list[str], start_index: int = 0) -> None:
        """Set the image list and navigate to start_index."""
        self._file_list = file_list

        # Shutdown old loader if any
        if self._loader is not None:
            self._loader.shutdown()

        preload = self._config.get("performance.preload_next_images", 5)
        retain = self._config.get("performance.retain_previous_images", 5)
        cache_mb = self._config.get("performance.image_cache_size_mb", 512)

        self._loader = ImageLoader(
            file_list,
            preload_next=preload,
            retain_previous=retain,
            cache_size_mb=cache_mb,
        )
        self._loader.image_ready.connect(self._on_image_ready)

        if file_list:
            self._image_loading = True
            self._loader.goto(start_index)

    @property
    def current_index(self) -> int:
        if self._loader:
            return self._loader.current_index
        return 0

    @property
    def canvas(self) -> ImageCanvas:
        return self._canvas

    @property
    def info_overlay(self) -> InfoOverlay:
        return self._info

    @property
    def is_loading(self) -> bool:
        return self._image_loading

    def navigate_next(self) -> None:
        if self._loader and not self._image_loading:
            self._image_loading = True
            self._loader.next()

    def navigate_prev(self) -> None:
        if self._loader and not self._image_loading:
            self._image_loading = True
            self._loader.previous()

    def navigate_next_folder(self) -> None:
        if self._loader and not self._image_loading:
            self._image_loading = True
            self._loader.next_folder()

    def navigate_prev_folder(self) -> None:
        if self._loader and not self._image_loading:
            self._image_loading = True
            self._loader.prev_folder()

    def goto(self, index: int) -> None:
        if self._loader:
            self._image_loading = True
            self._loader.goto(index)

    def shutdown(self) -> None:
        self._gif_player.stop()
        if self._loader:
            self._loader.shutdown()

    def _on_image_ready(self, index: int, pixmap: QPixmap) -> None:
        self._image_loading = False
        self._gif_player.stop()
        self._is_gif = False

        filepath = self._loader.current_filepath

        if filepath.lower().endswith(".gif"):
            if self._gif_player.load(filepath):
                self._is_gif = True
                self._gif_player.play()
                first = self._gif_player.first_frame()
                if first:
                    self._canvas.set_image(first)
                self._update_info()
                self.current_index_changed.emit(index)
                return

        self._canvas.set_image(pixmap)
        self._update_info()
        self.current_index_changed.emit(index)

    def _on_gif_frame(self, pixmap: QPixmap) -> None:
        self._canvas.set_frame(pixmap)

    def _update_info(self) -> None:
        if not self._loader:
            return
        filepath = self._loader.current_filepath
        p = Path(filepath) if filepath else None
        filename = p.name if p else ""
        folder = p.parent.name if p else ""
        pm = self._canvas._pixmap
        w = pm.width() if pm and not pm.isNull() else 0
        h = pm.height() if pm and not pm.isNull() else 0
        self._info.update_info(
            index=self._loader.current_index,
            total=self._loader.total,
            folder=folder,
            filename=filename,
            zoom_percent=int(self._canvas.zoom_factor * 100),
            width=w,
            height=h,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_info"):
            self._info.setGeometry(self._canvas.geometry())
