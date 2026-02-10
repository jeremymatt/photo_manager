"""Image information overlay with 4 display levels."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QFont, QColor, QFontMetrics
from PyQt6.QtWidgets import QWidget


class InfoOverlay(QWidget):
    """Semi-transparent overlay showing image information."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._visible = True
        self._level = 1  # 1, 2, 3, or 4
        self._index = 0
        self._total = 0
        self._folder = ""
        self._filename = ""
        self._zoom_percent = 100
        self._width = 0
        self._height = 0
        self._tags: list[str] = []

    @property
    def info_level(self) -> int:
        return self._level

    def toggle_visible(self) -> bool:
        self._visible = not self._visible
        self.update()
        return self._visible

    def cycle_level(self) -> int:
        self._level = (self._level % 4) + 1
        self.update()
        return self._level

    def set_tags(self, tags: list[str]) -> None:
        """Set the tag list displayed at level 4."""
        self._tags = tags
        self.update()

    def update_info(
        self,
        index: int = 0,
        total: int = 0,
        folder: str = "",
        filename: str = "",
        zoom_percent: int = 100,
        width: int = 0,
        height: int = 0,
    ) -> None:
        self._index = index
        self._total = total
        self._folder = folder
        self._filename = filename
        self._zoom_percent = zoom_percent
        self._width = width
        self._height = height
        self.update()

    def paintEvent(self, event) -> None:
        if not self._visible or self._total == 0:
            return

        text = self._build_text()
        if not text:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        painter.setFont(font)
        fm = QFontMetrics(font)

        padding = 8
        lines = text.split("\n")
        max_width = max(fm.horizontalAdvance(line) for line in lines)
        text_width = max_width + padding * 2
        line_height = fm.height()
        text_height = line_height * len(lines) + padding * 2

        # Position at upper-left
        x = 10
        y = 10

        # Background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 180))
        painter.drawRoundedRect(
            QRectF(x, y, text_width, text_height), 4, 4
        )

        # Text
        painter.setPen(QColor(255, 255, 255))
        for i, line in enumerate(lines):
            painter.drawText(
                int(x + padding),
                int(y + padding + fm.ascent() + i * line_height),
                line,
            )
        painter.end()

    def _build_text(self) -> str:
        parts = [f"[{self._index + 1}/{self._total}]"]
        if self._level >= 2:
            if self._folder:
                parts.append(f"{self._folder}/")
            parts.append(self._filename)
            parts.append(f"{self._zoom_percent}%")
        if self._level >= 3:
            parts.append(f"{self._width}\u00d7{self._height}")

        header = "  ".join(parts)

        if self._level >= 4 and self._tags:
            tag_lines = "\n".join(f"  {t}" for t in self._tags)
            return f"{header}\n{tag_lines}"

        return header
