"""
Centralized keyboard and hotkey management for the photo manager application.
Handles all keyboard shortcuts, custom hotkeys, and action delegation.
"""

import time
from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass

from PySide6.QtWidgets import QWidget, QShortcut, QMessageBox
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QKeySequence


@dataclass
class KeyAction:
    """Represents a keyboard action."""
    key_sequence: str
    action_name: str
    callback: Callable
    description: str
    category: str = "general"
    enabled: bool = True


class KeyboardHandler(QObject):
    """
    Centralized keyboard and hotkey management.
    Handles registration, conflict detection, and action delegation.
    """
    
    # Signals for different action categories
    navigation_action = Signal(str, dict)      # action_name, context
    image_action = Signal(str, dict)           # action_name, context  
    tag_action = Signal(str, dict)             # action_name, context
    file_action = Signal(str, dict)            # action_name, context
    view_action = Signal(str, dict)            # action_name, context
    
    def __init__(self, parent_widget: QWidget, config: Dict[str, Any]):
        super().__init__(parent_widget)
        
        self.parent_widget = parent_widget
        self.config = config
        
        # Storage for shortcuts and actions
        self.shortcuts: Dict[str, QShortcut] = {}
        self.actions: Dict[str, KeyAction] = {}
        self.key_conflicts: Dict[str, list[str]] = {}
        
        # Initialize shortcuts
        self._register_default_shortcuts()
        self._register_custom_hotkeys()
    
    def _register_default_shortcuts(self):
        """Register default application shortcuts."""
        
        # Navigation shortcuts
        navigation_shortcuts = [
            ("Right", "next_image", "Navigate to next image"),
            ("Left", "previous_image", "Navigate to previous image"),
            ("Shift+Right", "next_folder", "Navigate to next folder"),
            ("Shift+Left", "previous_folder", "Navigate to previous folder"),
            ("Home", "first_image", "Go to first image"),
            ("End", "last_image", "Go to last image"),
            ("Ctrl+F", "search_images", "Search images"),
        ]
        
        for key, action, desc in navigation_shortcuts:
            self._register_action(key, action, desc, "Navigation", self._emit_navigation_action)
        
        # Image manipulation shortcuts
        image_shortcuts = [
            ("Tab", "toggle_fit_mode", "Toggle image fit mode"),
            ("Up", "rotate_ccw", "Rotate counterclockwise"),
            ("Down", "rotate_cw", "Rotate clockwise"),
            ("+", "zoom_in", "Zoom in"),
            ("=", "zoom_in", "Zoom in (alternative)"),
            ("-", "zoom_out", "Zoom out"),
            ("Ctrl+0", "reset_view", "Reset image view"),
            ("Ctrl+R", "reset_transforms", "Reset all transformations"),
        ]
        
        for key, action, desc in image_shortcuts:
            self._register_action(key, action, desc, "Image", self._emit_image_action)
        
        # Tag management shortcuts
        tag_shortcuts = [
            ("Ctrl+T", "tag_image", "Tag current image"),
            ("Ctrl+C", "copy_tags", "Copy tags from current image"),
            ("Ctrl+V", "paste_tags", "Paste tags to current image"),
        ]
        
        for key, action, desc in tag_shortcuts:
            self._register_action(key, action, desc, "Tags", self._emit_tag_action)
        
        # File operation shortcuts
        file_shortcuts = [
            ("Delete", "mark_for_deletion", "Mark/unmark for deletion"),
            (".", "mark_for_deletion", "Mark/unmark for deletion (alternative)"),
            ("Ctrl+D", "delete_marked", "Delete marked files"),
            ("Ctrl+Z", "undo_action", "Undo last action"),
            ("Ctrl+O", "open_directory", "Open directory"),
        ]
        
        for key, action, desc in file_shortcuts:
            self._register_action(key, action, desc, "File", self._emit_file_action)
        
        # View shortcuts
        view_shortcuts = [
            ("F11", "toggle_fullscreen", "Toggle fullscreen"),
            ("F5", "start_slideshow", "Start slideshow"),
            ("Escape", "exit_fullscreen", "Exit fullscreen"),
            ("F1", "show_help", "Show keyboard shortcuts help"),
        ]
        
        for key, action, desc in view_shortcuts:
            self._register_action(key, action, desc, "View", self._emit_view_action)
        
        # GIF-specific shortcuts
        gif_shortcuts = [
            ("Space", "gif_play_pause", "Play/pause GIF animation"),
            ("Ctrl+Left", "gif_previous_frame", "Previous GIF frame"),
            ("Ctrl+Right", "gif_next_frame", "Next GIF frame"),
        ]
        
        for key, action, desc in gif_shortcuts:
            self._register_action(key, action, desc, "GIF", self._emit_image_action)
    
    def _register_custom_hotkeys(self):
        """Register custom hotkeys from configuration."""
        custom_hotkeys = self.config.get('hotkeys', {}).get('custom', {})
        
        for key_combo, tag_spec in custom_hotkeys.items():
            try:
                qt_key = self._convert_key_combo(key_combo)
                action_name = f"custom_tag_{key_combo}"
                description = f"Apply tag: {tag_spec}"
                
                def make_tag_callback(tag_specification):
                    def callback():
                        context = {'tag_spec': tag_specification}
                        self.tag_action.emit("apply_custom_tag", context)
                    return callback
                
                self._register_action(
                    qt_key, action_name, description, "Custom Tags", 
                    make_tag_callback(tag_spec)
                )
                
            except Exception as e:
                print(f"Error registering custom hotkey {key_combo}: {e}")
    
    def _register_action(self, key_sequence: str, action_name: str, description: str, 
                        category: str, callback: Callable):
        """Register a keyboard action."""
        try:
            # Check for conflicts
            if key_sequence in self.actions:
                self._handle_key_conflict(key_sequence, action_name)
                return
            
            # Create QShortcut
            shortcut = QShortcut(QKeySequence(key_sequence), self.parent_widget)
            shortcut.activated.connect(callback)
            
            # Store action info
            action = KeyAction(
                key_sequence=key_sequence,
                action_name=action_name,
                callback=callback,
                description=description,
                category=category
            )
            
            self.shortcuts[key_sequence] = shortcut
            self.actions[key_sequence] = action
            
        except Exception as e:
            print(f"Error registering shortcut {key_sequence}: {e}")
    
    def _handle_key_conflict(self, key_sequence: str, new_action: str):
        """Handle keyboard shortcut conflicts."""
        existing_action = self.actions[key_sequence].action_name
        
        if key_sequence not in self.key_conflicts:
            self.key_conflicts[key_sequence] = []
        
        self.key_conflicts[key_sequence].append(new_action)
        print(f"Keyboard conflict: {key_sequence} assigned to both '{existing_action}' and '{new_action}'")
    
    def _convert_key_combo(self, key_combo: str) -> str:
        """Convert key combination from config format to Qt format."""
        parts = key_combo.lower().split('_')
        result = []
        
        for part in parts:
            if part == 'shift':
                result.append('Shift')
            elif part == 'ctrl':
                result.append('Ctrl')
            elif part == 'alt':
                result.append('Alt')
            elif part == 'meta':
                result.append('Meta')
            else:
                result.append(part.upper())
        
        return '+'.join(result)
    
    def _get_action_name_from_sender(self) -> str:
        """Get action name from the shortcut that triggered the signal."""
        sender = self.sender()
        for key_seq, shortcut in self.shortcuts.items():
            if shortcut == sender:
                return self.actions[key_seq].action_name
        return "unknown_action"
    
    def _get_current_context(self) -> Dict[str, Any]:
        """Get current context information for actions."""
        return {
            'timestamp': time.time(),
            'has_focus': self.parent_widget.hasFocus(),
            'is_fullscreen': self.parent_widget.isFullScreen(),
            'window_size': (self.parent_widget.width(), self.parent_widget.height())
        }
    
    # Signal emission methods
    def _emit_navigation_action(self):
        """Emit navigation action signal."""
        action_name = self._get_action_name_from_sender()
        context = self._get_current_context()
        self.navigation_action.emit(action_name, context)
    
    def _emit_image_action(self):
        """Emit image manipulation action signal."""
        action_name = self._get_action_name_from_sender()
        context = self._get_current_context()
        self.image_action.emit(action_name, context)
    
    def _emit_tag_action(self):
        """Emit tag management action signal."""
        action_name = self._get_action_name_from_sender()
        context = self._get_current_context()
        self.tag_action.emit(action_name, context)
    
    def _emit_file_action(self):
        """Emit file operation action signal."""
        action_name = self._get_action_name_from_sender()
        context = self._get_current_context()
        self.file_action.emit(action_name, context)
    
    def _emit_view_action(self):
        """Emit view/window action signal."""
        action_name = self._get_action_name_from_sender()
        context = self._get_current_context()
        self.view_action.emit(action_name, context)
    
    # Public interface methods
    def add_custom_shortcut(self, key_sequence: str, action_name: str, 
                           callback: Callable, description: str = "", 
                           category: str = "Custom") -> bool:
        """
        Add a custom keyboard shortcut at runtime.
        
        Returns:
            bool: True if successfully added, False if conflict exists
        """
        if key_sequence in self.actions:
            return False
        
        try:
            self._register_action(key_sequence, action_name, description, category, callback)
            return True
        except Exception as e:
            print(f"Error adding custom shortcut: {e}")
            return False
    
    def remove_shortcut(self, key_sequence: str) -> bool:
        """Remove a keyboard shortcut."""
        if key_sequence not in self.shortcuts:
            return False
        
        try:
            self.shortcuts[key_sequence].deleteLater()
            del self.shortcuts[key_sequence]
            del self.actions[key_sequence]
            
            if key_sequence in self.key_conflicts:
                del self.key_conflicts[key_sequence]
            
            return True
        except Exception as e:
            print(f"Error removing shortcut: {e}")
            return False
    
    def enable_shortcut(self, key_sequence: str, enabled: bool = True):
        """Enable or disable a specific shortcut."""
        if key_sequence in self.shortcuts:
            self.shortcuts[key_sequence].setEnabled(enabled)
            self.actions[key_sequence].enabled = enabled
    
    def get_shortcuts_by_category(self, category: str) -> Dict[str, KeyAction]:
        """Get all shortcuts in a specific category."""
        return {
            key: action for key, action in self.actions.items() 
            if action.category == category
        }
    
    def get_all_shortcuts(self) -> Dict[str, KeyAction]:
        """Get all registered shortcuts."""
        return self.actions.copy()
    
    def get_conflicts(self) -> Dict[str, list[str]]:
        """Get all keyboard shortcut conflicts."""
        return self.key_conflicts.copy()
    
    def has_conflicts(self) -> bool:
        """Check if there are any keyboard conflicts."""
        return len(self.key_conflicts) > 0
    
    def validate_key_sequence(self, key_sequence: str) -> bool:
        """Validate a key sequence format."""
        try:
            QKeySequence(key_sequence)
            return True
        except:
            return False
    
    def get_shortcut_help(self) -> str:
        """Generate help text for all shortcuts."""
        help_sections = {}
        
        for action in self.actions.values():
            if action.category not in help_sections:
                help_sections[action.category] = []
            
            help_sections[action.category].append(
                f"  {action.key_sequence:<20} - {action.description}"
            )
        
        help_text = "Keyboard Shortcuts:\n\n"
        for category, shortcuts in help_sections.items():
            help_text += f"{category}:\n"
            help_text += "\n".join(shortcuts)
            help_text += "\n\n"
        
        return help_text
    
    def update_custom_hotkeys(self, new_hotkeys: Dict[str, str]):
        """Update custom hotkeys from new configuration."""
        # Remove existing custom hotkeys
        keys_to_remove = [
            key for key, action in self.actions.items() 
            if action.category == "Custom Tags"
        ]
        
        for key in keys_to_remove:
            self.remove_shortcut(key)
        
        # Add new custom hotkeys
        for key_combo, tag_spec in new_hotkeys.items():
            try:
                qt_key = self._convert_key_combo(key_combo)
                action_name = f"custom_tag_{key_combo}"
                description = f"Apply tag: {tag_spec}"
                
                def make_tag_callback(tag_specification):
                    def callback():
                        context = {'tag_spec': tag_specification}
                        self.tag_action.emit("apply_custom_tag", context)
                    return callback
                
                self._register_action(
                    qt_key, action_name, description, "Custom Tags",
                    make_tag_callback(tag_spec)
                )
                
            except Exception as e:
                print(f"Error registering custom hotkey {key_combo}: {e}")
    
    def set_context_mode(self, mode: str):
        """
        Set context mode to enable/disable certain shortcuts.
        
        Modes: 'normal', 'slideshow', 'fullscreen', 'gif_focus'
        """
        if mode == 'slideshow':
            self._disable_shortcuts_by_category(['File', 'Tags'])
        elif mode == 'gif_focus':
            self._enable_shortcuts_by_category(['GIF'])
        elif mode == 'normal':
            self._enable_all_shortcuts()
            self._disable_shortcuts_by_category(['GIF'])
        else:
            self._enable_all_shortcuts()
    
    def _enable_all_shortcuts(self):
        """Enable all registered shortcuts."""
        for shortcut in self.shortcuts.values():
            shortcut.setEnabled(True)
    
    def _disable_shortcuts_by_category(self, categories: list[str]):
        """Disable shortcuts in specific categories."""
        for action in self.actions.values():
            if action.category in categories:
                key = action.key_sequence
                if key in self.shortcuts:
                    self.shortcuts[key].setEnabled(False)
    
    def _enable_shortcuts_by_category(self, categories: list[str]):
        """Enable shortcuts in specific categories."""
        for action in self.actions.values():
            if action.category in categories:
                key = action.key_sequence
                if key in self.shortcuts:
                    self.shortcuts[key].setEnabled(True)


class ShortcutHelpDialog(QMessageBox):
    """Dialog showing all available keyboard shortcuts."""
    
    def __init__(self, keyboard_handler: KeyboardHandler, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("Keyboard Shortcuts")
        self.setIcon(QMessageBox.Information)
        
        help_text = keyboard_handler.get_shortcut_help()
        
        conflicts = keyboard_handler.get_conflicts()
        if conflicts:
            help_text += "\n⚠️ CONFLICTS DETECTED:\n"
            for key, actions in conflicts.items():
                help_text += f"  {key}: {', '.join(actions)}\n"
        
        self.setText("Keyboard Shortcuts Reference")
        self.setDetailedText(help_text)


def validate_custom_hotkey_config(hotkey_config: Dict[str, str]) -> Dict[str, list[str]]:
    """
    Validate custom hotkey configuration.
    
    Returns:
        Dict with 'valid' and 'invalid' keys listing validation results
    """
    valid_keys = []
    invalid_keys = []
    
    for key_combo, tag_spec in hotkey_config.items():
        try:
            # Validate tag specification format
            if '/' not in tag_spec:
                invalid_keys.append(f"{key_combo}: Invalid tag format (missing category/)")
                continue
            
            category, tag_name = tag_spec.split('/', 1)
            valid_categories = ['favorites', 'to_delete', 'scene_tags', 'event_tags', 'people_tags']
            
            if category not in valid_categories:
                invalid_keys.append(f"{key_combo}: Invalid category '{category}'")
                continue
            
            if not tag_name.strip():
                invalid_keys.append(f"{key_combo}: Empty tag name")
                continue
            
            valid_keys.append(key_combo)
            
        except Exception as e:
            invalid_keys.append(f"{key_combo}: {str(e)}")
    
    return {
        'valid': valid_keys,
        'invalid': invalid_keys
    }