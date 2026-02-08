"""Main window composing all viewer components."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent, QPixmap
from PyQt6.QtWidgets import QMainWindow, QInputDialog

from photo_manager.config.config import ConfigManager
from photo_manager.viewer.gif_player import GifPlayer
from photo_manager.viewer.help_overlay import HelpOverlay
from photo_manager.viewer.image_canvas import ImageCanvas
from photo_manager.viewer.image_loader import ImageLoader
from photo_manager.viewer.info_overlay import InfoOverlay
from photo_manager.viewer.key_handler import Action, KeyHandler
from photo_manager.viewer.slideshow import SlideshowController


class MainWindow(QMainWindow):
    """Photo viewer main window."""

    def __init__(
        self,
        file_list: list[str],
        config: ConfigManager | None = None,
        start_slideshow: bool = False,
        start_fullscreen: bool | None = None,
    ):
        super().__init__()
        self._config = config or ConfigManager()
        self._file_list = file_list

        # Window setup
        self.setWindowTitle("Photo Viewer")
        self.setStyleSheet("background-color: black;")
        w = self._config.get("ui.default_window_width", 1200)
        h = self._config.get("ui.default_window_height", 800)
        self.resize(w, h)

        # Canvas
        self._canvas = ImageCanvas(self)
        self.setCentralWidget(self._canvas)
        self._canvas.set_zoom_limits(
            self._config.get("ui.max_scroll_zoom_percent", 1000),
            self._config.get("ui.max_fit_to_screen_zoom_percent", 100),
        )

        # Image loader
        preload_next = self._config.get("performance.preload_next_images", 3)
        retain_prev = self._config.get("performance.retain_previous_images", 2)
        cache_mb = self._config.get("performance.image_cache_size_mb", 512)
        self._loader = ImageLoader(
            file_list,
            preload_next=preload_next,
            retain_previous=retain_prev,
            cache_size_mb=cache_mb,
        )
        self._loader.image_ready.connect(self._on_image_ready)

        # GIF player
        self._gif_player = GifPlayer(self)
        self._gif_player.frame_changed.connect(self._on_gif_frame)
        self._is_gif = False

        # Slideshow controller
        duration = self._config.get("slideshow.duration", 5.0)
        transition = self._config.get("slideshow.transition", "fade")
        trans_dur = self._config.get("slideshow.transition_duration", 1.0)
        loop = self._config.get("slideshow.loop", True)
        self._slideshow = SlideshowController(
            duration=duration,
            transition=transition,
            transition_duration=trans_dur,
            loop=loop,
            parent=self,
        )
        self._slideshow.advance.connect(self._on_slideshow_advance)
        self._slideshow.setup_fade_effect(self._canvas)

        # Info overlay
        self._info = InfoOverlay(self._canvas)
        info_level = self._config.get("ui.info_display_level", 1)
        # Set the initial level by cycling to the right one
        while self._info.info_level != info_level:
            self._info.cycle_level()

        # Help overlay
        self._help = HelpOverlay(self._canvas)

        # Key handler
        self._key_handler = KeyHandler(self)
        self._key_handler.action_triggered.connect(self._on_action)

        # Fullscreen
        fs = start_fullscreen
        if fs is None:
            fs = self._config.get("ui.start_fullscreen", True)
        if fs:
            self.showFullScreen()

        # Start slideshow if requested
        if start_slideshow:
            self._slideshow.start()

        # Load first image
        if file_list:
            self._loader.goto(0)

    def _on_image_ready(self, index: int, pixmap: QPixmap) -> None:
        """Called when an image is loaded and ready to display."""
        # Stop any playing GIF
        self._gif_player.stop()
        self._is_gif = False

        filepath = self._loader.current_filepath

        # Check if this is an animated GIF
        if filepath.lower().endswith(".gif"):
            if self._gif_player.load(filepath):
                self._is_gif = True
                self._gif_player.play()
                # Use first frame for canvas
                first = self._gif_player.first_frame()
                if first:
                    self._canvas.set_image(first)
                self._update_info()
                self._update_title()
                return

        self._canvas.set_image(pixmap)
        self._update_info()
        self._update_title()

        # Fade in if slideshow is active
        if self._slideshow.is_active:
            self._slideshow.trigger_fade_in()

    def _on_gif_frame(self, pixmap: QPixmap) -> None:
        self._canvas.set_frame(pixmap)

    def _on_slideshow_advance(self) -> None:
        self._loader.next()

    def _on_action(self, action: Action) -> None:
        # Dismiss help overlay on any action except toggle help
        if action != Action.TOGGLE_HELP and self._help.isVisible():
            self._help.dismiss()
            return

        if action == Action.NEXT_IMAGE:
            self._loader.next()
        elif action == Action.PREV_IMAGE:
            self._loader.previous()
        elif action == Action.NEXT_FOLDER:
            self._loader.next_folder()
        elif action == Action.PREV_FOLDER:
            self._loader.prev_folder()
        elif action == Action.ROTATE_CCW:
            self._canvas.rotate_ccw()
        elif action == Action.ROTATE_CW:
            self._canvas.rotate_cw()
        elif action == Action.BRIGHTNESS_UP:
            self._canvas.adjust_brightness(0.1)
        elif action == Action.BRIGHTNESS_DOWN:
            self._canvas.adjust_brightness(-0.1)
        elif action == Action.CONTRAST_UP:
            self._canvas.adjust_contrast(0.1)
        elif action == Action.CONTRAST_DOWN:
            self._canvas.adjust_contrast(-0.1)
        elif action == Action.CYCLE_ZOOM_MODE:
            self._canvas.cycle_zoom_mode()
            self._update_info()
        elif action == Action.GIF_SPEED_UP:
            if self._is_gif:
                self._gif_player.increase_speed()
        elif action == Action.GIF_SPEED_DOWN:
            if self._is_gif:
                self._gif_player.decrease_speed()
        elif action == Action.RESET_IMAGE:
            self._canvas.reset()
            self._update_info()
        elif action == Action.TOGGLE_INFO:
            self._info.toggle_visible()
        elif action == Action.CYCLE_INFO_LEVEL:
            self._info.cycle_level()
        elif action == Action.GOTO_IMAGE:
            self._goto_dialog()
        elif action == Action.TOGGLE_FULLSCREEN:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        elif action == Action.TOGGLE_RANDOM_ORDER:
            self._loader.toggle_random_order()
        elif action == Action.TOGGLE_HELP:
            self._help.toggle()
        elif action == Action.TOGGLE_SLIDESHOW_PAUSE:
            if self._slideshow.is_active:
                self._slideshow.toggle_pause()
            else:
                self._slideshow.start()
        elif action == Action.QUIT:
            self.close()

    def _goto_dialog(self) -> None:
        total = self._loader.total
        num, ok = QInputDialog.getInt(
            self, "Go to Image",
            f"Image number (1-{total}):",
            value=self._loader.current_index + 1,
            min=1, max=total,
        )
        if ok:
            self._loader.goto(num - 1)

    def _update_info(self) -> None:
        filepath = self._loader.current_filepath
        filename = Path(filepath).name if filepath else ""
        pm = self._canvas._pixmap
        w = pm.width() if pm and not pm.isNull() else 0
        h = pm.height() if pm and not pm.isNull() else 0
        self._info.update_info(
            index=self._loader.current_index,
            total=self._loader.total,
            filename=filename,
            zoom_percent=int(self._canvas.zoom_factor * 100),
            width=w,
            height=h,
        )

    def _update_title(self) -> None:
        filepath = self._loader.current_filepath
        filename = Path(filepath).name if filepath else "Photo Viewer"
        idx = self._loader.current_index + 1
        total = self._loader.total
        self.setWindowTitle(f"{filename} [{idx}/{total}] - Photo Viewer")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._key_handler.handle_key_event(event):
            super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Resize overlays to match canvas
        if hasattr(self, "_info"):
            self._info.setGeometry(self._canvas.geometry())
        if hasattr(self, "_help"):
            self._help.setGeometry(self._canvas.geometry())

    def closeEvent(self, event) -> None:
        self._gif_player.stop()
        self._slideshow.stop()
        self._loader.shutdown()
        super().closeEvent(event)
