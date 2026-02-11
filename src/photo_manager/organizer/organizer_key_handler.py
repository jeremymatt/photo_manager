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
    QUERY_FILTER = auto()

    # Tag management
    EDIT_TAGS = auto()
    EDIT_KEYBINDINGS = auto()
    QUICK_BINDING = auto()
    COPY_TAGS = auto()
    PASTE_TAGS = auto()
    APPLY_TAGS_TO_FOLDER = auto()
    SHOW_TAG_HOTKEYS = auto()

    # Delete workflow
    MARK_DELETE = auto()
    UNMARK_DELETE = auto()
    MARK_DELETE_FOLDER = auto()
    REVIEW_DELETIONS = auto()
    EXECUTE_DELETIONS = auto()

    # Duplicate management
    DETECT_DUPLICATES = auto()
    ENTER_DUP_REVIEW = auto()
    NEXT_DUP_GROUP = auto()
    PREV_DUP_GROUP = auto()
    TOGGLE_NOT_DUPLICATE = auto()
    KEEP_IMAGE = auto()

    # File operations
    SAVE_WITH_ROTATION = auto()

    QUIT = auto()


# Single-image view key map
_SINGLE_KEY_MAP: dict[tuple[int, frozenset], OrganizerAction] = {
    (Qt.Key.Key_Right, frozenset()): OrganizerAction.NEXT_IMAGE,
    (Qt.Key.Key_Left, frozenset()): OrganizerAction.PREV_IMAGE,
    (Qt.Key.Key_Right, frozenset({Qt.KeyboardModifier.AltModifier})): OrganizerAction.NEXT_FOLDER,
    (Qt.Key.Key_Left, frozenset({Qt.KeyboardModifier.AltModifier})): OrganizerAction.PREV_FOLDER,
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
    (Qt.Key.Key_T, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.EDIT_KEYBINDINGS,
    (Qt.Key.Key_F1, frozenset()): OrganizerAction.CHECK_ADD_DIRECTORY,
    (Qt.Key.Key_F2, frozenset()): OrganizerAction.EDIT_TAGS,
    (Qt.Key.Key_F4, frozenset()): OrganizerAction.IMPORT_DIRECTORY,
    (Qt.Key.Key_F5, frozenset()): OrganizerAction.QUERY_FILTER,
    (Qt.Key.Key_F9, frozenset()): OrganizerAction.CYCLE_INFO_LEVEL,
    (Qt.Key.Key_F10, frozenset()): OrganizerAction.GOTO_IMAGE,
    (Qt.Key.Key_F11, frozenset()): OrganizerAction.TOGGLE_FULLSCREEN,
    (Qt.Key.Key_F12, frozenset()): OrganizerAction.TOGGLE_RANDOM_ORDER,
    (Qt.Key.Key_M, frozenset({Qt.KeyboardModifier.AltModifier})): OrganizerAction.TOGGLE_HELP,
    (Qt.Key.Key_Space, frozenset()): OrganizerAction.TOGGLE_SLIDESHOW_PAUSE,
    (Qt.Key.Key_Period, frozenset()): OrganizerAction.MARK_DELETE,
    (Qt.Key.Key_Period, frozenset({Qt.KeyboardModifier.AltModifier})): OrganizerAction.UNMARK_DELETE,
    (Qt.Key.Key_C, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.COPY_TAGS,
    (Qt.Key.Key_V, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.PASTE_TAGS,
    (Qt.Key.Key_V, frozenset({Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier})): OrganizerAction.APPLY_TAGS_TO_FOLDER,
    (Qt.Key.Key_D, frozenset({Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.AltModifier})): OrganizerAction.MARK_DELETE_FOLDER,
    (Qt.Key.Key_D, frozenset({Qt.KeyboardModifier.AltModifier})): OrganizerAction.REVIEW_DELETIONS,
    (Qt.Key.Key_D, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.EXECUTE_DELETIONS,
    (Qt.Key.Key_T, frozenset({Qt.KeyboardModifier.AltModifier, Qt.KeyboardModifier.ShiftModifier})): OrganizerAction.SHOW_TAG_HOTKEYS,
    (Qt.Key.Key_D, frozenset({Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier})): OrganizerAction.DETECT_DUPLICATES,
    (Qt.Key.Key_F3, frozenset()): OrganizerAction.ENTER_DUP_REVIEW,
    (Qt.Key.Key_N, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.TOGGLE_NOT_DUPLICATE,
    (Qt.Key.Key_K, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.KEEP_IMAGE,
    (Qt.Key.Key_S, frozenset({Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier})): OrganizerAction.SAVE_WITH_ROTATION,
    (Qt.Key.Key_Escape, frozenset()): OrganizerAction.QUIT,
}

# Grid view key map (arrow keys handled by GridView itself)
_GRID_KEY_MAP: dict[tuple[int, frozenset], OrganizerAction] = {
    (Qt.Key.Key_Tab, frozenset()): OrganizerAction.TOGGLE_VIEW,
    (Qt.Key.Key_T, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.EDIT_KEYBINDINGS,
    (Qt.Key.Key_F1, frozenset()): OrganizerAction.CHECK_ADD_DIRECTORY,
    (Qt.Key.Key_F2, frozenset()): OrganizerAction.EDIT_TAGS,
    (Qt.Key.Key_F4, frozenset()): OrganizerAction.IMPORT_DIRECTORY,
    (Qt.Key.Key_F5, frozenset()): OrganizerAction.QUERY_FILTER,
    (Qt.Key.Key_F11, frozenset()): OrganizerAction.TOGGLE_FULLSCREEN,
    (Qt.Key.Key_M, frozenset({Qt.KeyboardModifier.AltModifier})): OrganizerAction.TOGGLE_HELP,
    (Qt.Key.Key_C, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.COPY_TAGS,
    (Qt.Key.Key_V, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.PASTE_TAGS,
    (Qt.Key.Key_V, frozenset({Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier})): OrganizerAction.APPLY_TAGS_TO_FOLDER,
    (Qt.Key.Key_Period, frozenset()): OrganizerAction.MARK_DELETE,
    (Qt.Key.Key_Period, frozenset({Qt.KeyboardModifier.AltModifier})): OrganizerAction.UNMARK_DELETE,
    (Qt.Key.Key_D, frozenset({Qt.KeyboardModifier.AltModifier})): OrganizerAction.REVIEW_DELETIONS,
    (Qt.Key.Key_D, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.EXECUTE_DELETIONS,
    (Qt.Key.Key_T, frozenset({Qt.KeyboardModifier.AltModifier, Qt.KeyboardModifier.ShiftModifier})): OrganizerAction.SHOW_TAG_HOTKEYS,
    (Qt.Key.Key_D, frozenset({Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier})): OrganizerAction.DETECT_DUPLICATES,
    (Qt.Key.Key_F3, frozenset()): OrganizerAction.ENTER_DUP_REVIEW,
    (Qt.Key.Key_Right, frozenset({Qt.KeyboardModifier.AltModifier})): OrganizerAction.NEXT_FOLDER,
    (Qt.Key.Key_Left, frozenset({Qt.KeyboardModifier.AltModifier})): OrganizerAction.PREV_FOLDER,
    (Qt.Key.Key_N, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.TOGGLE_NOT_DUPLICATE,
    (Qt.Key.Key_K, frozenset({Qt.KeyboardModifier.ControlModifier})): OrganizerAction.KEEP_IMAGE,
    (Qt.Key.Key_Escape, frozenset()): OrganizerAction.QUIT,
}

# Map for parsing key strings from config (e.g. "Ctrl+1" -> Qt key+modifier)
_KEY_NAME_MAP: dict[str, int] = {
    **{str(i): getattr(Qt.Key, f"Key_{i}") for i in range(10)},
    **{chr(c): getattr(Qt.Key, f"Key_{chr(c).upper()}") for c in range(ord("a"), ord("z") + 1)},
    ".": Qt.Key.Key_Period,
    ",": Qt.Key.Key_Comma,
    "/": Qt.Key.Key_Slash,
    ";": Qt.Key.Key_Semicolon,
    "'": Qt.Key.Key_Apostrophe,
    "[": Qt.Key.Key_BracketLeft,
    "]": Qt.Key.Key_BracketRight,
    "`": Qt.Key.Key_QuoteLeft,
    "\\": Qt.Key.Key_Backslash,
    "-": Qt.Key.Key_Minus,
    "=": Qt.Key.Key_Equal,
    "space": Qt.Key.Key_Space,
    **{f"f{i}": getattr(Qt.Key, f"Key_F{i}") for i in range(1, 13)},
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


_REVERSE_KEY_MAP: dict[int, str] = {v: k for k, v in _KEY_NAME_MAP.items()}
_REVERSE_MOD_MAP: dict[Qt.KeyboardModifier, str] = {
    v: k.capitalize() for k, v in _MOD_NAME_MAP.items()
}


def key_tuple_to_string(key_tuple: tuple[int, frozenset]) -> str:
    """Convert a (Qt.Key, frozenset of modifiers) to a human-readable string."""
    qt_key, mods = key_tuple
    parts = []
    for mod in sorted(mods, key=lambda m: m.value):
        parts.append(_REVERSE_MOD_MAP.get(mod, "?"))
    key_name = _REVERSE_KEY_MAP.get(qt_key)
    if key_name is None:
        key_name = f"0x{qt_key:x}"
    parts.append(key_name.upper() if len(key_name) == 1 else key_name)
    return "+".join(parts)


def _event_to_key_tuple(event: QKeyEvent) -> tuple[int, frozenset]:
    """Extract (key, modifiers) tuple from a QKeyEvent."""
    key = event.key()
    modifiers = event.modifiers()
    mod_set: set = set()
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        mod_set.add(Qt.KeyboardModifier.ControlModifier)
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        mod_set.add(Qt.KeyboardModifier.ShiftModifier)
    if modifiers & Qt.KeyboardModifier.AltModifier:
        mod_set.add(Qt.KeyboardModifier.AltModifier)
    return (key, frozenset(mod_set))


class OrganizerKeyHandler(QObject):
    """Context-aware keyboard routing for the organizer."""

    action_triggered = pyqtSignal(OrganizerAction)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid_mode = True
        self._last_event: QKeyEvent | None = None
        # Dynamic bindings: key tuple -> list of action strings
        self._binding_actions: dict[tuple[int, frozenset], list[str]] = {}
        # Track which keys were dynamically added so we can clean up
        self._dynamic_keys: list[tuple[int, frozenset]] = []

    @property
    def grid_mode(self) -> bool:
        return self._grid_mode

    @grid_mode.setter
    def grid_mode(self, value: bool) -> None:
        self._grid_mode = value

    def _clear_dynamic_bindings(self) -> None:
        """Remove previously loaded dynamic bindings from module-level maps."""
        for key in self._dynamic_keys:
            _SINGLE_KEY_MAP.pop(key, None)
            _GRID_KEY_MAP.pop(key, None)
        self._dynamic_keys.clear()
        self._binding_actions.clear()

    def load_all_bindings(self, config: ConfigManager) -> None:
        """Load all config-driven keybindings.

        Reads both quick_toggle_bindings and tag_keybindings from config.
        Each binding maps a key string to a list of action strings.
        """
        self._clear_dynamic_bindings()

        # Quick toggle bindings (primary system)
        quick = config.get("organizer.quick_toggle_bindings", {})
        if isinstance(quick, dict):
            for key_str, actions in quick.items():
                parsed = _parse_key_string(key_str)
                if parsed is None:
                    continue
                # Normalize: allow single string or list
                if isinstance(actions, str):
                    actions = [actions]
                if not isinstance(actions, list):
                    continue
                self._binding_actions[parsed] = actions
                _SINGLE_KEY_MAP[parsed] = OrganizerAction.QUICK_BINDING
                _GRID_KEY_MAP[parsed] = OrganizerAction.QUICK_BINDING
                self._dynamic_keys.append(parsed)

        # Legacy tag_keybindings (backward compat: value is a tag path string)
        legacy = config.get("organizer.tag_keybindings", {})
        if isinstance(legacy, dict):
            for key_str, tag_path in legacy.items():
                parsed = _parse_key_string(key_str)
                if parsed is None:
                    continue
                if not isinstance(tag_path, str):
                    continue
                self._binding_actions[parsed] = [f"tag:{tag_path}"]
                _SINGLE_KEY_MAP[parsed] = OrganizerAction.QUICK_BINDING
                _GRID_KEY_MAP[parsed] = OrganizerAction.QUICK_BINDING
                self._dynamic_keys.append(parsed)

    # Keep old name as alias
    load_custom_bindings = load_all_bindings

    def get_last_binding_actions(self) -> list[str]:
        """Get the action list for the last QUICK_BINDING key event."""
        if self._last_event is None:
            return []
        key_tuple = _event_to_key_tuple(self._last_event)
        return self._binding_actions.get(key_tuple, [])

    def handle_key_event(self, event: QKeyEvent) -> bool:
        """Process a key event. Returns True if an action was triggered."""
        lookup = _event_to_key_tuple(event)
        key_map = _GRID_KEY_MAP if self._grid_mode else _SINGLE_KEY_MAP
        action = key_map.get(lookup)
        if action is not None:
            self._last_event = event
            self.action_triggered.emit(action)
            return True
        return False
