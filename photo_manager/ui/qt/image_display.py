# image_display.py
"""
Image display widget with zoom, pan, rotate, brightness/contrast, and animated GIF support.
Handles all visual aspects of image presentation and manipulation.

Key features:
- Zoom beyond fit (in fit_to_window, fill_window, and actual_size)
- Mouse wheel zoom (up=in, down=out), anchored at pointer
- Click-drag panning
- Rotation for stills and animated GIFs
- Brightness & contrast (real LUT) for stills and animated GIF frames
- Keyboard: [ / ] brightness down/up; - / = or + contrast down/up (Shift = larger steps)
- ESC quits the application
- Background image loader with simple LRU cache
- GIF control overlay (play/pause, frame step, speed)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from PySide6.QtWidgets import (
    QLabel, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QApplication
)
from PySide6.QtCore import (
    Qt, QTimer, Signal, QThread, QPropertyAnimation, QEasingCurve,
    QPointF, QRectF
)
from PySide6.QtGui import (
    QPixmap, QMovie, QPainter, QTransform, QPaintEvent, QImage
)


# =============================================================================
# Background image loader with simple LRU cache
# =============================================================================
class ImageLoadWorker(QThread):
    """Background worker for loading images with basic caching."""
    image_loaded = Signal(str, QPixmap)    # path, pixmap
    gif_loaded = Signal(str, QMovie)       # path, movie
    loading_error = Signal(str, str)       # path, error message
    cache_updated = Signal(int)            # cache size

    def __init__(self, image_paths: list[str], cache_size: int = 10):
        super().__init__()
        self.image_paths = image_paths
        self.cache_size = cache_size
        self.should_stop = False
        self.image_cache: Dict[str, QPixmap | QMovie] = {}

    def run(self):
        for path in self.image_paths:
            if self.should_stop:
                break
            try:
                if path in self.image_cache:
                    item = self.image_cache[path]
                    if isinstance(item, QMovie):
                        self.gif_loaded.emit(path, item)
                    else:
                        self.image_loaded.emit(path, item)
                    continue

                if path.lower().endswith(".gif"):
                    movie = QMovie(path)
                    if movie.isValid():
                        self._add_to_cache(path, movie)
                        self.gif_loaded.emit(path, movie)
                    else:
                        self.loading_error.emit(path, "Invalid GIF file")
                else:
                    pm = QPixmap(path)
                    if not pm.isNull():
                        self._add_to_cache(path, pm)
                        self.image_loaded.emit(path, pm)
                    else:
                        self.loading_error.emit(path, "Invalid image")
            except Exception as e:
                self.loading_error.emit(path, str(e))

    def _add_to_cache(self, path: str, item: QPixmap | QMovie):
        if len(self.image_cache) >= self.cache_size:
            oldest = next(iter(self.image_cache))
            del self.image_cache[oldest]
        self.image_cache[path] = item
        self.cache_updated.emit(len(self.image_cache))

    def stop(self):
        self.should_stop = True

    def clear_cache(self):
        self.image_cache.clear()
        self.cache_updated.emit(0)


# =============================================================================
# GIF controls overlay (play/pause, step, speed)
# =============================================================================
class AnimatedGifHandler(QWidget):
    animation_state_changed = Signal(bool)  # is_playing

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.movie: Optional[QMovie] = None
        self.current_speed = 100  # percent
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        self.btn_prev = QPushButton("⏮️")
        self.btn_play = QPushButton("⏸️")
        self.btn_next = QPushButton("⏭️")
        self.btn_slow = QPushButton("🐌")
        self.btn_fast = QPushButton("🐰")

        for b in (self.btn_prev, self.btn_play, self.btn_next, self.btn_slow, self.btn_fast):
            b.setMaximumWidth(40)
            root.addWidget(b)

        root.addStretch()

        self.btn_prev.clicked.connect(self._prev)
        self.btn_play.clicked.connect(self._toggle)
        self.btn_next.clicked.connect(self._next)
        self.btn_slow.clicked.connect(self._slower)
        self.btn_fast.clicked.connect(self._faster)

        self.hide()

    def set_movie(self, movie: Optional[QMovie]):
        self.movie = movie
        if movie:
            self.show()
            self._refresh_play_label()
        else:
            self.hide()

    def _refresh_play_label(self):
        if not self.movie:
            return
        self.btn_play.setText("⏸️" if self.movie.state() == QMovie.Running else "▶️")

    def _toggle(self):
        if not self.movie:
            return
        if self.movie.state() == QMovie.Running:
            self.movie.setPaused(True)
            self.btn_play.setText("▶️")
            self.animation_state_changed.emit(False)
        else:
            self.movie.setPaused(False)
            self.btn_play.setText("⏸️")
            self.animation_state_changed.emit(True)

    def _prev(self):
        if self.movie:
            cur = self.movie.currentFrameNumber()
            self.movie.jumpToFrame(max(0, cur - 1))

    def _next(self):
        if self.movie:
            cur = self.movie.currentFrameNumber()
            total = self.movie.frameCount()
            if total > 0:
                self.movie.jumpToFrame(min(total - 1, cur + 1))
            else:
                self.movie.jumpToFrame(cur + 1)

    def _slower(self):
        self.current_speed = max(25, self.current_speed - 25)
        if self.movie:
            self.movie.setSpeed(self.current_speed)

    def _faster(self):
        self.current_speed = min(200, self.current_speed + 25)
        if self.movie:
            self.movie.setSpeed(self.current_speed)


# =============================================================================
# Main widget
# =============================================================================
class ImageDisplayWidget(QLabel):
    """
    Advanced image display widget handling stills & animated GIFs with:
    zoom/pan/rotation, brightness/contrast, and overlay GIF controls.
    """

    image_changed = Signal(str)      # image path
    transform_changed = Signal(dict) # zoom/rot/pan/bc/etc
    loading_started = Signal()
    loading_finished = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: black; color: white;")
        self.setMinimumSize(400, 300)
        self.setText("No image loaded")
        self.setFocusPolicy(Qt.StrongFocus)

        # Image state
        self.current_image_path: Optional[str] = None
        self.original_pixmap: Optional[QPixmap] = None
        self.current_movie: Optional[QMovie] = None
        self.is_animated_gif: bool = False

        # View transform
        self.zoom_factor: float = 1.0
        self.rotation_angle: float = 0.0
        self.pan_x: float = 0.0
        self.pan_y: float = 0.0
        self.fit_mode: str = "fit_to_window"  # fit_to_window | fill_window | actual_size

        # Brightness / Contrast in [-100 .. 100]
        self.brightness_adjustment: int = 0
        self.contrast_adjustment: int = 0

        # Zoom bounds
        self.min_zoom: float = 0.1
        self.max_zoom: float = 20.0

        # Panning interaction
        self._is_panning: bool = False
        self._last_mouse_pos: Optional[QPointF] = None

        # Cache for still-image brightness/contrast
        self._cached_adjusted_pixmap: Optional[QPixmap] = None
        self._cached_adjust_params: Tuple[int, int] = (0, 0)

        # GIF overlay
        self.gif_controls = AnimatedGifHandler(self)
        self.gif_controls.animation_state_changed.connect(self._on_gif_play_state)

        # Optional: double-click resets view
        self.enable_double_click_reset = True

        # Keyboard step sizes
        self._bc_step_small = 5
        self._bc_step_large = 10

    # -------------------------------------------------------------------------
    # Loading
    # -------------------------------------------------------------------------
    def load_image(self, image_path: str):
        """Load and display an image (stills or GIF)."""
        if not os.path.exists(image_path):
            self._show_error_message(f"File not found: {os.path.basename(image_path)}")
            return

        self.loading_started.emit()
        self.current_image_path = image_path

        try:
            self._clear_current()
            if image_path.lower().endswith(".gif"):
                self._load_gif(image_path)
            else:
                self._load_still(image_path)

            self.image_changed.emit(image_path)
        except Exception as e:
            self._show_error_message(f"Failed to load: {e}")
        finally:
            self.loading_finished.emit()

    def _clear_current(self):
        if self.current_movie:
            try:
                self.current_movie.stop()
                self.current_movie.frameChanged.disconnect(self._on_gif_frame)
                self.current_movie.finished.disconnect(self._on_gif_finished)
            except Exception:
                pass
        self.current_movie = None
        self.original_pixmap = None
        self.is_animated_gif = False
        self.gif_controls.set_movie(None)
        self.gif_controls.hide()
        self._invalidate_adjust_cache()
        self.clear()

    def _load_still(self, path: str):
        pm = QPixmap(path)
        if pm.isNull():
            self._show_error_message("Invalid image")
            return
        self.original_pixmap = pm
        self.is_animated_gif = False
        self._reset_view_keep_fit()
        self._invalidate_adjust_cache()
        self.gif_controls.hide()
        self._update_display()

    def _load_gif(self, path: str):
        movie = QMovie(path)
        if not movie.isValid():
            self._show_error_message("Invalid GIF file")
            return
        self.current_movie = movie
        self.is_animated_gif = True
        movie.frameChanged.connect(self._on_gif_frame)
        movie.finished.connect(self._on_gif_finished)
        movie.start()
        self.gif_controls.set_movie(movie)
        self.gif_controls.show()
        self._position_gif_controls()
        self._reset_view_keep_fit()
        self._invalidate_adjust_cache()
        self._update_display()

    # -------------------------------------------------------------------------
    # Transform plumbing
    # -------------------------------------------------------------------------
    def _show_error_message(self, msg: str):
        self.setText(f"Error: {msg}")
        self.setStyleSheet("background-color: black; color: red;")

    def _reset_view_keep_fit(self):
        self.zoom_factor = 1.0
        self.rotation_angle = 0.0
        self.pan_x = 0.0
        self.pan_y = 0.0

    def toggle_fit_mode(self):
        modes = ["fit_to_window", "actual_size", "fill_window"]
        i = modes.index(self.fit_mode)
        self.fit_mode = modes[(i + 1) % len(modes)]
        self._update_display()

    def set_zoom(self, zoom: float):
        self.zoom_factor = max(self.min_zoom, min(self.max_zoom, float(zoom)))
        self._update_display()

    def zoom_in(self, factor: float = 1.2):
        self.set_zoom(self.zoom_factor * factor)

    def zoom_out(self, factor: float = 1.2):
        self.set_zoom(self.zoom_factor / factor)

    def set_rotation(self, degrees: float):
        self.rotation_angle = float(degrees) % 360.0
        self._update_display()

    def rotate_clockwise(self, degrees: float = 90):
        self.set_rotation(self.rotation_angle + degrees)

    def rotate_counterclockwise(self, degrees: float = 90):
        self.set_rotation(self.rotation_angle - degrees)

    def adjust_brightness(self, val: int):
        self.brightness_adjustment = max(-100, min(100, int(val)))
        self._invalidate_adjust_cache()
        self._update_display()

    def adjust_contrast(self, val: int):
        self.contrast_adjustment = max(-100, min(100, int(val)))
        self._invalidate_adjust_cache()
        self._update_display()

    def _update_display(self):
        """Trigger repaint and emit transform state."""
        self.update()
        self.transform_changed.emit(self.get_transform_info())

    # -------------------------------------------------------------------------
    # Brightness / Contrast (real LUT)
    # -------------------------------------------------------------------------
    def _invalidate_adjust_cache(self):
        self._cached_adjusted_pixmap = None
        self._cached_adjust_params = (self.brightness_adjustment, self.contrast_adjustment)

    def _build_lut(self, brightness: int, contrast: int):
        """
        Returns 256-length LUT for brightness/contrast.
        brightness [-100,100] -> offset in [-255,255]
        contrast   [-100,100] -> slope via standard formula
        """
        offset = int(brightness * 255 / 100)
        cpx = int(contrast * 255 / 100)
        # https://stackoverflow.com/a/324612
        cf = (259 * (cpx + 255)) / (255 * (259 - cpx)) if cpx != 255 else 1e6
        lut = [0] * 256
        for i in range(256):
            v = int(cf * (i - 128) + 128 + offset)
            if v < 0:
                v = 0
            elif v > 255:
                v = 255
            lut[i] = v
        return lut

    def _apply_bc_to_qimage(self, qimg: QImage, brightness: int, contrast: int) -> QImage:
        if brightness == 0 and contrast == 0:
            return qimg
        img = qimg.convertToFormat(QImage.Format_ARGB32)
        lut = self._build_lut(brightness, contrast)
        w, h = img.width(), img.height()
        for y in range(h):
            row = memoryview(img.scanLine(y)).cast("B")
            for x in range(0, w * 4, 4):
                # BGRA layout on little endian
                row[x + 0] = lut[row[x + 0]]  # B
                row[x + 1] = lut[row[x + 1]]  # G
                row[x + 2] = lut[row[x + 2]]  # R
        return img

    def _current_source_pixmap(self) -> Optional[QPixmap]:
        """Return source pixmap for painting with brightness/contrast applied."""
        b, c = self.brightness_adjustment, self.contrast_adjustment

        if self.is_animated_gif and self.current_movie:
            img = self.current_movie.currentImage()
            if img.isNull():
                return None
            if b == 0 and c == 0:
                return QPixmap.fromImage(img)
            adj = self._apply_bc_to_qimage(img, b, c)
            return QPixmap.fromImage(adj)

        if self.original_pixmap is None or self.original_pixmap.isNull():
            return None
        if b == 0 and c == 0:
            return self.original_pixmap

        if self._cached_adjusted_pixmap is not None and self._cached_adjust_params == (b, c):
            return self._cached_adjusted_pixmap

        base_img = self.original_pixmap.toImage()
        adj_img = self._apply_bc_to_qimage(base_img, b, c)
        self._cached_adjusted_pixmap = QPixmap.fromImage(adj_img)
        self._cached_adjust_params = (b, c)
        return self._cached_adjusted_pixmap

    # -------------------------------------------------------------------------
    # Geometry helpers
    # -------------------------------------------------------------------------
    def _image_size(self) -> Tuple[int, int]:
        if self.is_animated_gif and self.current_movie:
            img = self.current_movie.currentImage()
            if not img.isNull():
                return img.width(), img.height()
            return 0, 0
        if self.original_pixmap:
            return self.original_pixmap.width(), self.original_pixmap.height()
        return 0, 0

    def _fit_base_scale(self, w: int, h: int) -> float:
        if w == 0 or h == 0:
            return 1.0
        vw = max(1, self.width())
        vh = max(1, self.height())
        if self.fit_mode == "fill_window":
            return max(vw / w, vh / h)
        if self.fit_mode == "actual_size":
            return 1.0
        return min(vw / w, vh / h)  # fit_to_window

    def _effective_scale(self, w: int, h: int) -> float:
        return self._fit_base_scale(w, h) * max(self.min_zoom, min(self.max_zoom, self.zoom_factor))

    def _auto_center_offset(self, sw: float, sh: float) -> Tuple[float, float]:
        ox = (self.width() - sw) * 0.5 if sw < self.width() else 0.0
        oy = (self.height() - sh) * 0.5 if sh < self.height() else 0.0
        return ox, oy

    # -------------------------------------------------------------------------
    # Painting
    # -------------------------------------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)

        iw, ih = self._image_size()
        if iw == 0 or ih == 0:
            return

        src_pm = self._current_source_pixmap()
        if src_pm is None or src_pm.isNull():
            return

        scale = self._effective_scale(iw, ih)
        sw, sh = iw * scale, ih * scale
        auto_ox, auto_oy = self._auto_center_offset(sw, sh)

        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform, on=True)

        # translate -> center -> rotate -> scale, then draw with center origin
        painter.translate(auto_ox + self.pan_x, auto_oy + self.pan_y)
        painter.translate(sw * 0.5, sh * 0.5)
        if self.rotation_angle:
            painter.rotate(self.rotation_angle)
        painter.scale(scale, scale)

        target = QRectF(-iw * 0.5, -ih * 0.5, iw, ih)
        painter.drawPixmap(target, src_pm, QRectF(src_pm.rect()))
        painter.end()

    # -------------------------------------------------------------------------
    # Interaction
    # -------------------------------------------------------------------------
    def wheelEvent(self, event):
        """Mouse wheel zoom; anchored to cursor (approx in unrotated space)."""
        iw, ih = self._image_size()
        if iw == 0 or ih == 0:
            return

        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta == 0:
            return
        step = 1.1 if delta > 0 else (1.0 / 1.1)

        pos = event.position()
        cx, cy = float(pos.x()), float(pos.y())

        old_scale = self._effective_scale(iw, ih)
        old_sw, old_sh = iw * old_scale, ih * old_scale
        old_auto_ox, old_auto_oy = self._auto_center_offset(old_sw, old_sh)
        ox_old = old_auto_ox + self.pan_x
        oy_old = old_auto_oy + self.pan_y

        # Map cursor to image coords (approx, ignoring rotation for speed)
        img_x = (cx - ox_old - old_sw * 0.5) / old_scale + (iw * 0.5)
        img_y = (cy - oy_old - old_sh * 0.5) / old_scale + (ih * 0.5)

        new_zoom = max(self.min_zoom, min(self.max_zoom, self.zoom_factor * step))
        if new_zoom == self.zoom_factor:
            return
        self.zoom_factor = new_zoom

        new_scale = self._effective_scale(iw, ih)
        new_sw, new_sh = iw * new_scale, ih * new_scale
        new_auto_ox, new_auto_oy = self._auto_center_offset(new_sw, new_sh)

        # Keep same image point under cursor (approx)
        self.pan_x = cx - new_auto_ox - (img_x - iw * 0.5) * new_scale - new_sw * 0.5
        self.pan_y = cy - new_auto_oy - (img_y - ih * 0.5) * new_scale - new_sh * 0.5

        self._update_display()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_panning = True
            self._last_mouse_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_panning and self._last_mouse_pos is not None:
            pos = event.position()
            dx = float(pos.x() - self._last_mouse_pos.x())
            dy = float(pos.y() - self._last_mouse_pos.y())
            self.pan_x += dx
            self.pan_y += dy
            self._last_mouse_pos = pos
            self._update_display()
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_panning = False
            self._last_mouse_pos = None
            self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.enable_double_click_reset and event.button() == Qt.LeftButton:
            self._reset_view_keep_fit()
            self._update_display()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        """
        Keyboard:
          Esc           -> quit app
          [ / ]         -> brightness -/+ (Shift = larger step)
          - / = or +    -> contrast   -/+ (Shift = larger step; NumPad supported)
        """
        key = event.key()
        mods = event.modifiers()
        big = bool(mods & Qt.ShiftModifier)
        bstep = self._bc_step_large if big else self._bc_step_small
        cstep = self._bc_step_large if big else self._bc_step_small

        if key == Qt.Key_Escape:
            app = QApplication.instance()
            if app is not None:
                app.quit()
            return

        # Brightness controls: [ and ]
        if key == Qt.Key_BracketLeft:
            self.adjust_brightness(self.brightness_adjustment - bstep)
            return
        if key == Qt.Key_BracketRight:
            self.adjust_brightness(self.brightness_adjustment + bstep)
            return

        # Contrast controls: -, =, + (including keypad)
        if key in (Qt.Key_Minus, Qt.Key_Underscore):
            self.adjust_contrast(self.contrast_adjustment - cstep)
            return
        if key in (Qt.Key_Equal, Qt.Key_Plus):
            self.adjust_contrast(self.contrast_adjustment + cstep)
            return

        # Some keyboards send Plus/Minus from keypad via the same keys, but to be safe:
        if key == Qt.KeypadModifier and event.text() in ['+', '-']:
            if event.text() == '+':
                self.adjust_contrast(self.contrast_adjustment + cstep)
            else:
                self.adjust_contrast(self.contrast_adjustment - cstep)
            return

        super().keyPressEvent(event)

    # -------------------------------------------------------------------------
    # Resize / overlay placement
    # -------------------------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.gif_controls.isVisible():
            self._position_gif_controls()
        self._update_display()

    def _position_gif_controls(self):
        h = self.gif_controls.sizeHint().height()
        self.gif_controls.setGeometry(0, self.height() - h, self.width(), h)

    # -------------------------------------------------------------------------
    # GIF callbacks
    # -------------------------------------------------------------------------
    def _on_gif_frame(self, _frame: int):
        self._update_display()

    def _on_gif_finished(self):
        if self.current_movie:
            self.current_movie.start()

    def _on_gif_play_state(self, _is_playing: bool):
        pass

    # -------------------------------------------------------------------------
    # Introspection / utilities
    # -------------------------------------------------------------------------
    def has_image(self) -> bool:
        return (self.original_pixmap is not None and not self.original_pixmap.isNull()) or (
            self.current_movie is not None and self.current_movie.isValid()
        )

    def get_transform_info(self) -> Dict[str, Any]:
        return {
            "image_path": self.current_image_path,
            "is_animated_gif": self.is_animated_gif,
            "zoom_factor": self.zoom_factor,
            "rotation_angle": self.rotation_angle,
            "brightness": self.brightness_adjustment,
            "contrast": self.contrast_adjustment,
            "fit_mode": self.fit_mode,
            "pan_x": self.pan_x,
            "pan_y": self.pan_y,
        }

    def get_original_size(self) -> Tuple[int, int]:
        iw, ih = self._image_size()
        return iw, ih

    def get_current_size(self) -> Tuple[int, int]:
        iw, ih = self._image_size()
        if iw == 0 or ih == 0:
            return 0, 0
        s = self._effective_scale(iw, ih)
        return int(iw * s), int(ih * s)

    def save_current_view(self, save_path: str) -> bool:
        """
        Save current view to file by rendering to an offscreen image.
        Includes transforms & current GIF frame.
        """
        try:
            canvas = QImage(self.size(), QImage.Format_ARGB32_Premultiplied)
            canvas.fill(0)
            painter = QPainter(canvas)
            # Draw background/children (incl. overlay controls)
            self.render(painter)
            painter.end()

            # Draw the image content using same pipeline as paintEvent
            iw, ih = self._image_size()
            if iw == 0 or ih == 0:
                return False
            src_pm = self._current_source_pixmap()
            if src_pm is None or src_pm.isNull():
                return False

            scale = self._effective_scale(iw, ih)
            sw, sh = iw * scale, ih * scale
            auto_ox, auto_oy = self._auto_center_offset(sw, sh)

            painter = QPainter(canvas)
            painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform, on=True)
            painter.translate(auto_ox + self.pan_x, auto_oy + self.pan_y)
            painter.translate(sw * 0.5, sh * 0.5)
            if self.rotation_angle:
                painter.rotate(self.rotation_angle)
            painter.scale(scale, scale)
            painter.drawPixmap(QRectF(-iw * 0.5, -ih * 0.5, iw, ih), src_pm, QRectF(src_pm.rect()))
            painter.end()

            return canvas.save(save_path)
        except Exception as e:
            print(f"Error saving image: {e}")
            return False


# =============================================================================
# Helper utilities
# =============================================================================
def create_thumbnail(image_path: str, size: Tuple[int, int] = (128, 128)) -> Optional[QPixmap]:
    """Create a thumbnail for a still image or the first frame of a GIF."""
    try:
        if image_path.lower().endswith(".gif"):
            movie = QMovie(image_path)
            if movie.isValid():
                movie.jumpToFrame(0)
                pm = movie.currentPixmap()
                if not pm.isNull():
                    return pm.scaled(size[0], size[1], Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            pm = QPixmap(image_path)
            if not pm.isNull():
                return pm.scaled(size[0], size[1], Qt.KeepAspectRatio, Qt.SmoothTransformation)
    except Exception as e:
        print(f"Error creating thumbnail: {e}")
    return None


def get_image_info(image_path: str) -> Dict[str, Any]:
    """Return basic info about an image file (works for GIFs too)."""
    info: Dict[str, Any] = {
        "file_path": image_path,
        "filename": os.path.basename(image_path),
        "exists": os.path.exists(image_path),
        "is_gif": image_path.lower().endswith(".gif"),
    }
    try:
        if info["exists"]:
            st = os.stat(image_path)
            info["file_size"] = st.st_size
            info["modified_time"] = st.st_mtime

            if info["is_gif"]:
                movie = QMovie(image_path)
                if movie.isValid():
                    info["frame_count"] = movie.frameCount()
                    movie.jumpToFrame(0)
                    img = movie.currentImage()
                    info["width"] = img.width()
                    info["height"] = img.height()
            else:
                pm = QPixmap(image_path)
                if not pm.isNull():
                    info["width"] = pm.width()
                    info["height"] = pm.height()
    except Exception as e:
        info["error"] = str(e)
    return info
