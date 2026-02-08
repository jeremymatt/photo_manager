"""Keyboard event routing for the organizer application."""

from __future__ import annotations

from enum import Enum, auto

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QKeyEvent

from photo_manager.config.config import ConfigManager


class OrganizerAction(Enum):
    # Navigation (single-image view)
    NEXT_IMAGE = auto()
    PREV_IMAGE = auto()
    NEXT_FOLDER = auto()
    PREV_FOLDER = auto()

    # Image adjustments
    ROTATE_CCW = auto()
    ROTATE_CW = auto()
    BRIGHTNESS_UP = auto()
    BRIGHTNESS_DOWN = auto()
    CONTRAST_UP = auto()
    CONTRAST_DOWN = auto()
    CYCLE_ZOOM_MODE = auto()

    # GIF
    GIF_SPEED_UP = auto()
    GIF_SPEED_DOWN = auto()

    # Display
    RESET_IMAGE = auto()
    TOGGLE_INFO = auto()
    CYCLE_INFO_LEVEL = auto()
    GOTO_IMAGE = auto()
    TOGGLE_FULLSCREEN = auto()
    TOGGLE_RANDOM_ORDER = auto()
    TOGGLE_HELP = auto()
    TOGGLE_SLIDESHOW_PAUSE = auto()

    # Organizer-specific
    TOGGLE_VIEW = auto()
    IMPORT_DIRECTORY = auto()
    CHECK_ADD_DIRECTORY = auto()

    # Tag management
    EDIT_TAGS = auto()
    TOGGLE_FAVORITE = auto()
    TOGGLE_DELETE = auto()
    TOGGLE_REVIEWED = auto()
    TOGGLE_CUSTOM_TAG = auto()

    QUIT = auto()


# Single-image view key map
_SINGLE_KEY_MAP: dict[tuple[int, frozenset], OrganizerAction] = {
    (Qt.Key.Key_Right, frozenset()): OrganizerAction.NEXT_IMAGE,
    (Qt.Key.Key_Left, frozenset()): OrganizerAction.PREV_IMAGE,
    (Qt.Key.Key_Right, frozenset({Qt.KeyboardModifier.ShiftModifier})): OrganizerAction.NEXT_FOLDER,
    (Qt.Key.Key_Left, frozenset({Qt.KeyboardModifier.ShiftModifier})): OrganizerAction.PREV_FOLDER,
    (Qt.Key.Key_Up, frozenset()): OrganizerAction.ROTATE_CCW,
    (Qt.Key.Key_Down, frozenset()): OrganizerAction.ROTATE_CW,
    (Qt.Key.Key_Up, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.BRIGHTNESS_UP,
    (Qt.Key.Key_Down, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.BRIGHTNESS_DOWN,
    (Qt.Key.Key_Up, frozenset({Qt.KeyboardModifier.AltModifier})): OrganizerAction.CONTRAST_UP,
    (Qt.Key.Key_Down, frozenset({Qt.KeyboardModifier.AltModifier})): OrganizerAction.CONTRAST_DOWN,
    (Qt.Key.Key_Tab, frozenset()): OrganizerAction.TOGGLE_VIEW,
    (Qt.Key.Key_Plus, frozenset()): OrganizerAction.GIF_SPEED_UP,
    (Qt.Key.Key_Equal, frozenset()): OrganizerAction.GIF_SPEED_UP,
    (Qt.Key.Key_Minus, frozenset()): OrganizerAction.GIF_SPEED_DOWN,
    (Qt.Key.Key_R, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.RESET_IMAGE,
    (Qt.Key.Key_I, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.TOGGLE_INFO,
    (Qt.Key.Key_F1, frozenset()): OrganizerAction.CHECK_ADD_DIRECTORY,
    (Qt.Key.Key_F2, frozenset()): OrganizerAction.EDIT_TAGS,
    (Qt.Key.Key_F4, frozenset()): OrganizerAction.IMPORT_DIRECTORY,
    (Qt.Key.Key_F9, frozenset()): OrganizerAction.CYCLE_INFO_LEVEL,
    (Qt.Key.Key_F10, frozenset()): OrganizerAction.GOTO_IMAGE,
    (Qt.Key.Key_F11, frozenset()): OrganizerAction.TOGGLE_FULLSCREEN,
    (Qt.Key.Key_F12, frozenset()): OrganizerAction.TOGGLE_RANDOM_ORDER,
    (Qt.Key.Key_M, frozenset({Qt.KeyboardModifier.AltModifier})): OrganizerAction.TOGGLE_HELP,
    (Qt.Key.Key_Space, frozenset()): OrganizerAction.TOGGLE_SLIDESHOW_PAUSE,
    (Qt.Key.Key_F, frozenset()): OrganizerAction.TOGGLE_FAVORITE,
    (Qt.Key.Key_D, frozenset()): OrganizerAction.TOGGLE_DELETE,
    (Qt.Key.Key_R, frozenset()): OrganizerAction.TOGGLE_REVIEWED,
    (Qt.Key.Key_Escape, frozenset()): OrganizerAction.QUIT,
}

# Grid view key map (arrow keys handled by GridView itself)
_GRID_KEY_MAP: dict[tuple[int, frozenset], OrganizerAction] = {
    (Qt.Key.Key_Tab, frozenset()): OrganizerAction.TOGGLE_VIEW,
    (Qt.Key.Key_F1, frozenset()): OrganizerAction.CHECK_ADD_DIRECTORY,
    (Qt.Key.Key_F2, frozenset()): OrganizerAction.EDIT_TAGS,
    (Qt.Key.Key_F4, frozenset()): OrganizerAction.IMPORT_DIRECTORY,
    (Qt.Key.Key_F11, frozenset()): OrganizerAction.TOGGLE_FULLSCREEN,
    (Qt.Key.Key_M, frozenset({Qt.KeyboardModifier.AltModifier})): OrganizerAction.TOGGLE_HELP,
    (Qt.Key.Key_F, frozenset()): OrganizerAction.TOGGLE_FAVORITE,
    (Qt.Key.Key_D, frozenset()): OrganizerAction.TOGGLE_DELETE,
    (Qt.Key.Key_R, frozenset()): OrganizerAction.TOGGLE_REVIEWED,
    (Qt.Key.Key_Escape, frozenset()): OrganizerAction.QUIT,
}

# Map for parsing key strings from config (e.g. "Ctrl+1" -> Qt key+modifier)
_KEY_NAME_MAP: dict[str, int] = {
    **{str(i): getattr(Qt.Key, f"Key_{i}") for i in range(10)},
    **{chr(c): getattr(Qt.Key, f"Key_{chr(c).upper()}") for c in range(ord("a"), ord("z") + 1)},
}

_MOD_NAME_MAP: dict[str, Qt.KeyboardModifier] = {
    "ctrl": Qt.KeyboardModifier.ControlModifier,
    "shift": Qt.KeyboardModifier.ShiftModifier,
    "alt": Qt.KeyboardModifier.AltModifier,
}


def _parse_key_string(key_str: str) -> tuple[int, frozenset] | None:
    """Parse a key string like 'Ctrl+1' into (Qt.Key, frozenset of modifiers)."""
    parts = [p.strip().lower() for p in key_str.split("+")]
    mods: set = set()
    key = None

    for part in parts:
        if part in _MOD_NAME_MAP:
            mods.add(_MOD_NAME_MAP[part])
        elif part in _KEY_NAME_MAP:
            key = _KEY_NAME_MAP[part]

    if key is None:
        return None
    return (key, frozenset(mods))


class OrganizerKeyHandler(QObject):
    """Context-aware keyboard routing for the organizer."""

    action_triggered = pyqtSignal(OrganizerAction)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid_mode = True
        # Custom tag keybinding: key tuple -> tag path
        self._custom_tag_bindings: dict[tuple[int, frozenset], str] = {}
        # Last key event for resolving custom tag bindings
        self._last_event: QKeyEvent | None = None

    @property
    def grid_mode(self) -> bool:
        return self._grid_mode

    @grid_mode.setter
    def grid_mode(self, value: bool) -> None:
        self._grid_mode = value

    def load_custom_bindings(self, config: ConfigManager) -> None:
        """Load custom tag keybindings from config.

        Config format: organizer.tag_keybindings = {"Ctrl+1": "person.Alice"}
        """
        bindings = config.get("organizer.tag_keybindings", {})
        if not isinstance(bindings, dict):
            return

        for key_str, tag_path in bindings.items():
            parsed = _parse_key_string(key_str)
            if parsed is None:
                continue
            self._custom_tag_bindings[parsed] = tag_path
            # Add to both key maps
            _SINGLE_KEY_MAP[parsed] = OrganizerAction.TOGGLE_CUSTOM_TAG
            _GRID_KEY_MAP[parsed] = OrganizerAction.TOGGLE_CUSTOM_TAG

    def get_custom_tag_path(self, event: QKeyEvent) -> str | None:
        """Get the tag path for a custom keybinding, if any."""
        key = event.key()
        modifiers = event.modifiers()
        mod_set: set = set()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            mod_set.add(Qt.KeyboardModifier.ControlModifier)
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            mod_set.add(Qt.KeyboardModifier.ShiftModifier)
        if modifiers & Qt.KeyboardModifier.AltModifier:
            mod_set.add(Qt.KeyboardModifier.AltModifier)
        return self._custom_tag_bindings.get((key, frozenset(mod_set)))

    def handle_key_event(self, event: QKeyEvent) -> bool:
        """Process a key event. Returns True if an action was triggered."""
        key = event.key()
        modifiers = event.modifiers()

        mod_set: set = set()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            mod_set.add(Qt.KeyboardModifier.ControlModifier)
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            mod_set.add(Qt.KeyboardModifier.ShiftModifier)
        if modifiers & Qt.KeyboardModifier.AltModifier:
            mod_set.add(Qt.KeyboardModifier.AltModifier)

        lookup = (key, frozenset(mod_set))
        key_map = _GRID_KEY_MAP if self._grid_mode else _SINGLE_KEY_MAP
        action = key_map.get(lookup)
        if action is not None:
            self._last_event = event
            self.action_triggered.emit(action)
            return True
        return False

    def get_last_custom_tag_path(self) -> str | None:
        """Get the tag path for the last TOGGLE_CUSTOM_TAG event."""
        if self._last_event is None:
            return None
        return self.get_custom_tag_path(self._last_event)
