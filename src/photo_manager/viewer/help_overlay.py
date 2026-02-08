"""Keyboard shortcut help overlay."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QFont, QColor, QFontMetrics
from PyQt6.QtWidgets import QWidget


HELP_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Navigation", [
        ("Right / Left", "Next / previous image"),
        ("Shift+Right / Left", "Next / previous folder"),
        ("F10", "Go to image number"),
        ("F12", "Toggle sequential / random"),
    ]),
    ("Display", [
        ("Up / Down", "Rotate CCW / CW"),
        ("Ctrl+Up / Down", "Brightness up / down"),
        ("Alt+Up / Down", "Contrast up / down"),
        ("Tab", "Cycle zoom mode"),
        ("Mouse Wheel", "Zoom in / out"),
        ("Click + Drag", "Pan image"),
        ("Ctrl+R", "Reset image"),
        ("Ctrl+I", "Toggle info display"),
        ("F9", "Cycle info detail level"),
        ("F11", "Toggle fullscreen"),
    ]),
    ("Slideshow / GIF", [
        ("Space", "Toggle slideshow pause"),
        ("+ / =", "Increase GIF speed"),
        ("- / _", "Decrease GIF speed"),
    ]),
    ("Other", [
        ("Alt+M", "Show / hide this help"),
        ("Esc", "Quit"),
    ]),
]


class HelpOverlay(QWidget):
    """Full-screen help overlay showing keyboard shortcuts."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._visible = False
        self.hide()

    def toggle(self) -> bool:
        self._visible = not self._visible
        if self._visible:
            self.show()
            self.raise_()
        else:
            self.hide()
        self.update()
        return self._visible

    def dismiss(self) -> None:
        self._visible = False
        self.hide()

    def paintEvent(self, event) -> None:
        if not self._visible:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Semi-transparent background
        painter.fillRect(self.rect(), QColor(0, 0, 0, 200))

        header_font = QFont("Segoe UI", 14, QFont.Weight.Bold)
        header_font.setStyleHint(QFont.StyleHint.SansSerif)
        body_font = QFont("Consolas", 11)
        body_font.setStyleHint(QFont.StyleHint.Monospace)
        title_font = QFont("Segoe UI", 18, QFont.Weight.Bold)
        title_font.setStyleHint(QFont.StyleHint.SansSerif)

        header_fm = QFontMetrics(header_font)
        body_fm = QFontMetrics(body_font)

        key_col_width = 200
        desc_col_width = 250
        total_width = key_col_width + desc_col_width
        x_start = (self.width() - total_width) // 2
        y = 60

        # Title
        painter.setFont(title_font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(
            x_start, y, "Keyboard Shortcuts"
        )
        y += 40

        for section_name, shortcuts in HELP_SECTIONS:
            # Section header
            painter.setFont(header_font)
            painter.setPen(QColor(100, 180, 255))
            painter.drawText(x_start, y, section_name)
            y += header_fm.height() + 4

            # Shortcuts
            painter.setFont(body_font)
            for key, description in shortcuts:
                painter.setPen(QColor(200, 200, 100))
                painter.drawText(x_start + 10, y, key)
                painter.setPen(QColor(220, 220, 220))
                painter.drawText(x_start + key_col_width, y, description)
                y += body_fm.height() + 2

            y += 12  # Section spacing

        painter.end()

    def keyPressEvent(self, event) -> None:
        self.dismiss()

    def mousePressEvent(self, event) -> None:
        self.dismiss()
