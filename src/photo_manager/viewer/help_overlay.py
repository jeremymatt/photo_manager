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

    def __init__(
        self,
        parent: QWidget | None = None,
        sections: list[tuple[str, list[tuple[str, str]]]] | None = None,
    ):
        super().__init__(parent)
        self._sections = sections or HELP_SECTIONS
        self._default_sections = self._sections
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._visible = False
        self.hide()

    def update_sections(
        self,
        sections: list[tuple[str, list[tuple[str, str]]]],
    ) -> None:
        """Replace the displayed sections temporarily."""
        self._sections = sections
        self.update()

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
        self._sections = self._default_sections
        self.hide()

    def _section_height(
        self, section: tuple[str, list[tuple[str, str]]],
        header_fm: QFontMetrics, body_fm: QFontMetrics,
    ) -> int:
        """Calculate pixel height of a single section."""
        _, shortcuts = section
        h = header_fm.height() + 4  # header line
        h += len(shortcuts) * (body_fm.height() + 2)  # shortcut lines
        h += 12  # section spacing
        return h

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
        col_width = key_col_width + desc_col_width
        col_gap = 40
        title_height = 50  # title + spacing
        top_margin = 60

        available_height = self.height() - top_margin - 40  # bottom margin

        # Calculate section heights and distribute into columns
        section_heights = [
            self._section_height(s, header_fm, body_fm)
            for s in self._sections
        ]
        total_content = sum(section_heights)

        # Determine number of columns needed
        if total_content + title_height <= available_height:
            num_cols = 1
        elif total_content + title_height <= available_height * 2:
            num_cols = 2
        else:
            num_cols = 3

        # Distribute sections into columns (greedy fill)
        col_limit = (available_height - title_height) if num_cols == 1 else available_height
        columns: list[list[int]] = [[]]  # lists of section indices
        col_h = 0
        for i, sh in enumerate(section_heights):
            if col_h + sh > col_limit and columns[-1] and len(columns) < num_cols:
                columns.append([])
                col_h = 0
            columns[-1].append(i)
            col_h += sh

        # Center all columns as a group
        total_width = len(columns) * col_width + (len(columns) - 1) * col_gap
        x_base = (self.width() - total_width) // 2

        # Title (above first column or centered)
        painter.setFont(title_font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(x_base, top_margin, "Keyboard Shortcuts")

        # Draw each column
        for col_idx, section_indices in enumerate(columns):
            x_start = x_base + col_idx * (col_width + col_gap)
            y = top_margin + title_height if col_idx == 0 else top_margin

            for si in section_indices:
                section_name, shortcuts = self._sections[si]

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
