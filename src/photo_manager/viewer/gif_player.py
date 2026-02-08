"""Animated GIF frame controller."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap

from photo_manager.viewer.image_loader import pil_to_qpixmap


class GifPlayer(QObject):
    """Plays animated GIF files frame by frame."""

    frame_changed = pyqtSignal(QPixmap)
    loop_completed = pyqtSignal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)
        self._frames: list[QPixmap] = []
        self._durations: list[int] = []  # ms per frame
        self._current_frame = 0
        self._speed_factor = 1.0
        self._playing = False
        self._filepath: str = ""

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    @property
    def speed_factor(self) -> float:
        return self._speed_factor

    def load(self, filepath: str | Path) -> bool:
        """Load an animated GIF. Returns True if the file is animated."""
        self.stop()
        self._frames.clear()
        self._durations.clear()
        self._current_frame = 0
        self._filepath = str(filepath)

        try:
            img = Image.open(filepath)
            if not getattr(img, "is_animated", False):
                img.close()
                return False

            n_frames = getattr(img, "n_frames", 1)
            for i in range(n_frames):
                img.seek(i)
                frame = img.copy()
                if frame.mode != "RGBA":
                    frame = frame.convert("RGBA")
                self._frames.append(pil_to_qpixmap(frame))
                duration = img.info.get("duration", 100)
                self._durations.append(max(duration, 10))

            img.close()
            return len(self._frames) > 1

        except Exception:
            self._frames.clear()
            self._durations.clear()
            return False

    def play(self) -> None:
        if not self._frames:
            return
        self._playing = True
        self._current_frame = 0
        self.frame_changed.emit(self._frames[0])
        self._schedule_next()

    def stop(self) -> None:
        self._timer.stop()
        self._playing = False

    def pause(self) -> None:
        self._timer.stop()
        self._playing = False

    def resume(self) -> None:
        if self._frames:
            self._playing = True
            self._schedule_next()

    def increase_speed(self) -> float:
        self._speed_factor = min(self._speed_factor * 1.25, 5.0)
        if self._playing:
            self._schedule_next()
        return self._speed_factor

    def decrease_speed(self) -> float:
        self._speed_factor = max(self._speed_factor / 1.25, 0.1)
        if self._playing:
            self._schedule_next()
        return self._speed_factor

    def first_frame(self) -> QPixmap | None:
        """Get the first frame as a QPixmap."""
        return self._frames[0] if self._frames else None

    def _advance_frame(self) -> None:
        if not self._frames:
            return
        self._current_frame += 1
        if self._current_frame >= len(self._frames):
            self._current_frame = 0
            self.loop_completed.emit()

        self.frame_changed.emit(self._frames[self._current_frame])
        self._schedule_next()

    def _schedule_next(self) -> None:
        if not self._frames or not self._playing:
            return
        duration = self._durations[self._current_frame]
        adjusted = max(int(duration / self._speed_factor), 10)
        self._timer.start(adjusted)
