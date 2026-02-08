"""Configuration manager for Photo Manager."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "database": {
        "path": ".photo_manager.db",
        "auto_cleanup_missing": False,
        "backup_on_startup": True,
    },
    "duplicate_detection": {
        "hash_algorithms": ["phash", "dhash"],
        "similarity_threshold": 5,
        "auto_detect": True,
        "background_processing": True,
    },
    "file_scanning": {
        "supported_formats": [
            "jpg", "jpeg", "png", "gif", "bmp",
            "tiff", "tif", "webp", "ico",
        ],
        "ignore_patterns": ["Thumbs.db", ".DS_Store"],
        "ignore_hidden_files": True,
        "include_subdirectories": True,
        "max_file_size_mb": 500,
    },
    "hotkeys": {
        "custom": {},
    },
    "performance": {
        "background_threads": 2,
        "image_cache_size_mb": 512,
        "preload_next_images": 3,
        "retain_previous_images": 2,
        "thumbnail_size": [256, 256],
        "preload_timeout_seconds": 30,
    },
    "slideshow": {
        "duration": 5.0,
        "transition": "fade",
        "transition_duration": 1.0,
        "loop": True,
        "random_order": False,
        "show_info": False,
        "gif_animation_speed": 1,
        "include_subfolders": True,
    },
    "ui": {
        "default_window_width": 1200,
        "default_window_height": 800,
        "default_zoom": "fit_to_canvas",
        "start_fullscreen": True,
        "theme": "dark",
        "undo_queue_size": 1000,
        "info_display_level": 1,
        "max_scroll_zoom_percent": 1000,
        "max_fit_to_screen_zoom_percent": 100,
    },
    "logging": {
        "level": "INFO",
        "log_to_file": False,
        "log_file": "photo_manager.log",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class ConfigManager:
    """Load, save, and access YAML configuration with defaults."""

    def __init__(self, config_path: str | Path | None = None):
        self._path = Path(config_path) if config_path else None
        self._config: dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        if self._path and self._path.exists():
            self.load()

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    def load(self, config_path: str | Path | None = None) -> None:
        """Load config from YAML file, merging with defaults."""
        path = Path(config_path) if config_path else self._path
        if path is None:
            raise ValueError("No config path specified")
        self._path = path
        with open(path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        self._config = _deep_merge(DEFAULT_CONFIG, user_config)

    def save(self, config_path: str | Path | None = None) -> None:
        """Save current config to YAML file."""
        path = Path(config_path) if config_path else self._path
        if path is None:
            raise ValueError("No config path specified")
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self._config, f, default_flow_style=False, sort_keys=False)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Get a config value using dotted notation (e.g. 'ui.default_zoom')."""
        keys = dotted_key.split(".")
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def set(self, dotted_key: str, value: Any) -> None:
        """Set a config value using dotted notation."""
        keys = dotted_key.split(".")
        target = self._config
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value

    def reset(self) -> None:
        """Reset config to defaults."""
        self._config = copy.deepcopy(DEFAULT_CONFIG)
