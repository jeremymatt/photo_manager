"""Slideshow controller with timer-based advancement and transitions."""

from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget


class SlideshowController(QObject):
    """Controls automatic image advancement in slideshow mode."""

    advance = pyqtSignal()  # Emitted when it's time for the next image

    def __init__(
        self,
        duration: float = 5.0,
        transition: str = "fade",
        transition_duration: float = 1.0,
        loop: bool = True,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._duration_ms = int(duration * 1000)
        self._transition = transition
        self._transition_duration_ms = int(transition_duration * 1000)
        self._loop = loop
        self._active = False
        self._paused = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

        self._fade_animation: QPropertyAnimation | None = None
        self._opacity_effect: QGraphicsOpacityEffect | None = None

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def transition_type(self) -> str:
        return self._transition

    def start(self) -> None:
        self._active = True
        self._paused = False
        self._schedule_advance()

    def stop(self) -> None:
        self._active = False
        self._paused = False
        self._timer.stop()

    def toggle_pause(self) -> bool:
        """Toggle pause state. Returns new paused state."""
        if not self._active:
            return False
        self._paused = not self._paused
        if self._paused:
            self._timer.stop()
        else:
            self._schedule_advance()
        return self._paused

    def notify_gif_loop(self) -> None:
        """Called when a GIF completes one loop. Advances if duration has also passed."""
        # If slideshow is active, the timer handles advancement
        pass

    def setup_fade_effect(self, widget: QWidget) -> None:
        """Set up opacity effect on the canvas widget for fade transitions."""
        self._opacity_effect = QGraphicsOpacityEffect(widget)
        self._opacity_effect.setOpacity(1.0)
        widget.setGraphicsEffect(self._opacity_effect)

    def trigger_fade_in(self) -> None:
        """Animate the canvas fading in after a new image is loaded."""
        if self._transition != "fade" or self._opacity_effect is None:
            return

        if self._fade_animation is not None:
            self._fade_animation.stop()

        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_animation.setDuration(self._transition_duration_ms)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._fade_animation.start()

    def trigger_fade_out(self, on_finished=None) -> None:
        """Animate the canvas fading out before switching images."""
        if self._transition != "fade" or self._opacity_effect is None:
            if on_finished:
                on_finished()
            return

        if self._fade_animation is not None:
            self._fade_animation.stop()

        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_animation.setDuration(self._transition_duration_ms)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        if on_finished:
            self._fade_animation.finished.connect(on_finished)
        self._fade_animation.start()

    def _schedule_advance(self) -> None:
        if self._active and not self._paused:
            self._timer.start(self._duration_ms)

    def _on_timeout(self) -> None:
        if self._active and not self._paused:
            if self._transition == "fade":
                self.trigger_fade_out(on_finished=self._emit_advance_and_fade_in)
            else:
                self.advance.emit()
                self._schedule_advance()

    def _emit_advance_and_fade_in(self) -> None:
        self.advance.emit()
        self.trigger_fade_in()
        self._schedule_advance()
