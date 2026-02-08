"""Centralized keyboard and mouse event routing."""

from __future__ import annotations

from enum import Enum, auto

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QKeyEvent


class Action(Enum):
    NEXT_IMAGE = auto()
    PREV_IMAGE = auto()
    NEXT_FOLDER = auto()
    PREV_FOLDER = auto()
    ROTATE_CCW = auto()
    ROTATE_CW = auto()
    BRIGHTNESS_UP = auto()
    BRIGHTNESS_DOWN = auto()
    CONTRAST_UP = auto()
    CONTRAST_DOWN = auto()
    CYCLE_ZOOM_MODE = auto()
    GIF_SPEED_UP = auto()
    GIF_SPEED_DOWN = auto()
    RESET_IMAGE = auto()
    TOGGLE_INFO = auto()
    CYCLE_INFO_LEVEL = auto()
    GOTO_IMAGE = auto()
    TOGGLE_FULLSCREEN = auto()
    TOGGLE_RANDOM_ORDER = auto()
    TOGGLE_HELP = auto()
    TOGGLE_SLIDESHOW_PAUSE = auto()
    QUIT = auto()


# Mapping: (Qt.Key, frozenset of modifiers) → Action
_KEY_MAP: dict[tuple[int, frozenset], Action] = {
    (Qt.Key.Key_Right, frozenset()): Action.NEXT_IMAGE,
    (Qt.Key.Key_Left, frozenset()): Action.PREV_IMAGE,
    (Qt.Key.Key_Right, frozenset({Qt.KeyboardModifier.ShiftModifier})): Action.NEXT_FOLDER,
    (Qt.Key.Key_Left, frozenset({Qt.KeyboardModifier.ShiftModifier})): Action.PREV_FOLDER,
    (Qt.Key.Key_Up, frozenset()): Action.ROTATE_CCW,
    (Qt.Key.Key_Down, frozenset()): Action.ROTATE_CW,
    (Qt.Key.Key_Up, frozenset({Qt.KeyboardModifier.ControlModifier})): Action.BRIGHTNESS_UP,
    (Qt.Key.Key_Down, frozenset({Qt.KeyboardModifier.ControlModifier})): Action.BRIGHTNESS_DOWN,
    (Qt.Key.Key_Up, frozenset({Qt.KeyboardModifier.AltModifier})): Action.CONTRAST_UP,
    (Qt.Key.Key_Down, frozenset({Qt.KeyboardModifier.AltModifier})): Action.CONTRAST_DOWN,
    (Qt.Key.Key_Tab, frozenset()): Action.CYCLE_ZOOM_MODE,
    (Qt.Key.Key_Plus, frozenset()): Action.GIF_SPEED_UP,
    (Qt.Key.Key_Equal, frozenset()): Action.GIF_SPEED_UP,
    (Qt.Key.Key_Minus, frozenset()): Action.GIF_SPEED_DOWN,
    (Qt.Key.Key_R, frozenset({Qt.KeyboardModifier.ControlModifier})): Action.RESET_IMAGE,
    (Qt.Key.Key_I, frozenset({Qt.KeyboardModifier.ControlModifier})): Action.TOGGLE_INFO,
    (Qt.Key.Key_F9, frozenset()): Action.CYCLE_INFO_LEVEL,
    (Qt.Key.Key_F10, frozenset()): Action.GOTO_IMAGE,
    (Qt.Key.Key_F11, frozenset()): Action.TOGGLE_FULLSCREEN,
    (Qt.Key.Key_F12, frozenset()): Action.TOGGLE_RANDOM_ORDER,
    (Qt.Key.Key_M, frozenset({Qt.KeyboardModifier.AltModifier})): Action.TOGGLE_HELP,
    (Qt.Key.Key_Space, frozenset()): Action.TOGGLE_SLIDESHOW_PAUSE,
    (Qt.Key.Key_Escape, frozenset()): Action.QUIT,
}


class KeyHandler(QObject):
    """Routes keyboard events to named actions via signals."""

    action_triggered = pyqtSignal(Action)

    def handle_key_event(self, event: QKeyEvent) -> bool:
        """Process a key event. Returns True if an action was triggered."""
        key = event.key()
        modifiers = event.modifiers()

        # Build modifier set (ignore KeypadModifier)
        mod_set: set = set()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            mod_set.add(Qt.KeyboardModifier.ControlModifier)
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            mod_set.add(Qt.KeyboardModifier.ShiftModifier)
        if modifiers & Qt.KeyboardModifier.AltModifier:
            mod_set.add(Qt.KeyboardModifier.AltModifier)

        lookup = (key, frozenset(mod_set))
        action = _KEY_MAP.get(lookup)
        if action is not None:
            self.action_triggered.emit(action)
            return True
        return False
