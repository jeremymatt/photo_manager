"""Image canvas widget with zoom, pan, rotation, and brightness/contrast."""

from __future__ import annotations

from enum import Enum, auto

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPainter, QPixmap, QTransform, QWheelEvent, QMouseEvent
from PyQt6.QtWidgets import QWidget


class ZoomMode(Enum):
    ORIGINAL = auto()      # 100% (1:1 pixels)
    FIT_TO_CANVAS = auto()  # Scale to fit entirely within canvas
    FILL_CANVAS = auto()    # Scale to fill canvas (may crop)


class ImageCanvas(QWidget):
    """Widget that displays an image with zoom, pan, rotation, and adjustments."""

    ZOOM_STEP = 1.15  # 15% per scroll notch

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

        self._pixmap: QPixmap | None = None
        self._zoom_mode = ZoomMode.FIT_TO_CANVAS
        self._zoom_factor = 1.0
        self._rotation = 0  # degrees, multiples of 90
        self._brightness = 0.0  # -1.0 to 1.0
        self._contrast = 0.0   # -1.0 to 1.0
        self._pan_offset = QPointF(0, 0)
        self._dragging = False
        self._drag_start = QPointF()
        self._pan_at_drag_start = QPointF()

        # Zoom limits
        self._max_scroll_zoom = 10.0  # 1000%
        self._max_fit_zoom = 1.0      # 100%

        # Adjusted pixmap (with brightness/contrast applied)
        self._adjusted_pixmap: QPixmap | None = None
        self._adjustments_dirty = True

    def set_zoom_limits(
        self, max_scroll_percent: int, max_fit_percent: int
    ) -> None:
        self._max_scroll_zoom = max_scroll_percent / 100.0
        self._max_fit_zoom = max_fit_percent / 100.0

    def set_image(self, pixmap: QPixmap) -> None:
        """Set a new image to display."""
        self._pixmap = pixmap
        self._adjustments_dirty = True
        self._pan_offset = QPointF(0, 0)
        self._rotation = 0
        self._brightness = 0.0
        self._contrast = 0.0
        self._compute_base_zoom()
        self.update()

    def set_frame(self, pixmap: QPixmap) -> None:
        """Set a GIF frame without resetting zoom/pan/rotation."""
        self._pixmap = pixmap
        self._adjustments_dirty = True
        self.update()

    def clear(self) -> None:
        self._pixmap = None
        self._adjusted_pixmap = None
        self.update()

    # --- Zoom ---

    @property
    def zoom_factor(self) -> float:
        return self._zoom_factor

    @property
    def zoom_mode(self) -> ZoomMode:
        return self._zoom_mode

    def cycle_zoom_mode(self) -> ZoomMode:
        """Cycle through zoom modes: original → fit → fill → original."""
        modes = [ZoomMode.ORIGINAL, ZoomMode.FIT_TO_CANVAS, ZoomMode.FILL_CANVAS]
        idx = modes.index(self._zoom_mode)
        self._zoom_mode = modes[(idx + 1) % len(modes)]
        self._pan_offset = QPointF(0, 0)
        self._compute_base_zoom()
        self.update()
        return self._zoom_mode

    def _compute_base_zoom(self) -> None:
        """Compute zoom factor based on current zoom mode."""
        if self._pixmap is None or self._pixmap.isNull():
            self._zoom_factor = 1.0
            return

        img_w, img_h = self._rotated_size()
        canvas_w, canvas_h = self.width(), self.height()

        if canvas_w <= 0 or canvas_h <= 0:
            self._zoom_factor = 1.0
            return

        if self._zoom_mode == ZoomMode.ORIGINAL:
            self._zoom_factor = 1.0
        elif self._zoom_mode == ZoomMode.FIT_TO_CANVAS:
            fit = min(canvas_w / img_w, canvas_h / img_h)
            self._zoom_factor = min(fit, self._max_fit_zoom)
        elif self._zoom_mode == ZoomMode.FILL_CANVAS:
            fill = max(canvas_w / img_w, canvas_h / img_h)
            self._zoom_factor = min(fill, self._max_fit_zoom)

    def _rotated_size(self) -> tuple[float, float]:
        """Get image dimensions after rotation."""
        if self._pixmap is None:
            return (0, 0)
        w, h = self._pixmap.width(), self._pixmap.height()
        if self._rotation % 180 != 0:
            w, h = h, w
        return (w, h)

    # --- Rotation ---

    @property
    def rotation(self) -> int:
        return self._rotation

    def rotate_cw(self) -> None:
        self._rotation = (self._rotation + 90) % 360
        self._pan_offset = QPointF(0, 0)
        self._compute_base_zoom()
        self.update()

    def rotate_ccw(self) -> None:
        self._rotation = (self._rotation - 90) % 360
        self._pan_offset = QPointF(0, 0)
        self._compute_base_zoom()
        self.update()

    # --- Brightness / Contrast ---

    @property
    def brightness(self) -> float:
        return self._brightness

    @property
    def contrast(self) -> float:
        return self._contrast

    def adjust_brightness(self, delta: float) -> None:
        self._brightness = max(-1.0, min(1.0, self._brightness + delta))
        self._adjustments_dirty = True
        self.update()

    def adjust_contrast(self, delta: float) -> None:
        self._contrast = max(-1.0, min(1.0, self._contrast + delta))
        self._adjustments_dirty = True
        self.update()

    # --- Reset ---

    def reset(self) -> None:
        """Reset zoom, rotation, brightness, contrast, and pan."""
        self._rotation = 0
        self._brightness = 0.0
        self._contrast = 0.0
        self._pan_offset = QPointF(0, 0)
        self._adjustments_dirty = True
        self._compute_base_zoom()
        self.update()

    # --- Paint ---

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Black background
        painter.fillRect(self.rect(), Qt.GlobalColor.black)

        pm = self._get_display_pixmap()
        if pm is None or pm.isNull():
            painter.end()
            return

        img_w, img_h = self._rotated_size()
        scaled_w = img_w * self._zoom_factor
        scaled_h = img_h * self._zoom_factor

        # Center the image, then apply pan offset
        x = (self.width() - scaled_w) / 2 + self._pan_offset.x()
        y = (self.height() - scaled_h) / 2 + self._pan_offset.y()

        painter.translate(x + scaled_w / 2, y + scaled_h / 2)
        painter.rotate(self._rotation)
        painter.scale(self._zoom_factor, self._zoom_factor)
        painter.translate(-pm.width() / 2, -pm.height() / 2)
        painter.drawPixmap(0, 0, pm)
        painter.end()

    def _get_display_pixmap(self) -> QPixmap | None:
        if self._pixmap is None:
            return None
        if not self._adjustments_dirty and self._adjusted_pixmap is not None:
            return self._adjusted_pixmap

        if abs(self._brightness) < 0.001 and abs(self._contrast) < 0.001:
            self._adjusted_pixmap = self._pixmap
        else:
            self._adjusted_pixmap = self._apply_adjustments(self._pixmap)
        self._adjustments_dirty = False
        return self._adjusted_pixmap

    def _apply_adjustments(self, pixmap: QPixmap) -> QPixmap:
        """Apply brightness/contrast adjustments using PIL."""
        from PIL import Image, ImageEnhance

        # QPixmap → QImage → PIL
        qimage = pixmap.toImage()
        qimage = qimage.convertToFormat(QImage.Format.Format_RGBA8888)
        width, height = qimage.width(), qimage.height()
        ptr = qimage.bits()
        ptr.setsize(qimage.sizeInBytes())
        pil_img = Image.frombuffer("RGBA", (width, height), bytes(ptr), "raw", "RGBA", 0, 1)

        # Apply brightness (1.0 = original, 0.0 = black, 2.0 = double)
        if abs(self._brightness) > 0.001:
            factor = 1.0 + self._brightness  # range 0.0 to 2.0
            pil_img = ImageEnhance.Brightness(pil_img).enhance(factor)

        # Apply contrast
        if abs(self._contrast) > 0.001:
            factor = 1.0 + self._contrast
            pil_img = ImageEnhance.Contrast(pil_img).enhance(factor)

        # PIL → QPixmap
        from photo_manager.viewer.image_loader import pil_to_qpixmap
        return pil_to_qpixmap(pil_img)

    # --- Mouse events ---

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._pixmap is None:
            return

        # Get mouse position relative to image center before zoom
        mouse_pos = event.position()
        old_zoom = self._zoom_factor

        # Compute new zoom
        degrees = event.angleDelta().y()
        if degrees > 0:
            new_zoom = old_zoom * self.ZOOM_STEP
        else:
            new_zoom = old_zoom / self.ZOOM_STEP

        # Clamp zoom
        new_zoom = max(0.01, min(new_zoom, self._max_scroll_zoom))
        self._zoom_factor = new_zoom

        # Adjust pan to keep the point under the cursor stationary
        if old_zoom > 0:
            scale_ratio = new_zoom / old_zoom
            img_center_x = self.width() / 2 + self._pan_offset.x()
            img_center_y = self.height() / 2 + self._pan_offset.y()
            dx = mouse_pos.x() - img_center_x
            dy = mouse_pos.y() - img_center_y
            self._pan_offset = QPointF(
                self._pan_offset.x() - dx * (scale_ratio - 1),
                self._pan_offset.y() - dy * (scale_ratio - 1),
            )

        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start = event.position()
            self._pan_at_drag_start = QPointF(self._pan_offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            delta = event.position() - self._drag_start
            self._pan_offset = QPointF(
                self._pan_at_drag_start.x() + delta.x(),
                self._pan_at_drag_start.y() + delta.y(),
            )
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def resizeEvent(self, event) -> None:
        self._compute_base_zoom()
        super().resizeEvent(event)


# Need this import for _apply_adjustments
from PyQt6.QtGui import QImage
