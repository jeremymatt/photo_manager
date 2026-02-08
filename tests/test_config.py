"""Tests for ConfigManager."""

import tempfile
from pathlib import Path

import pytest

from photo_manager.config.config import ConfigManager, DEFAULT_CONFIG


class TestConfigManager:
    def test_default_config(self):
        cm = ConfigManager()
        assert cm.get("ui.default_zoom") == "fit_to_canvas"
        assert cm.get("database.path") == ".photo_manager.db"
        assert cm.get("performance.preload_next_images") == 3

    def test_get_dotted_key(self):
        cm = ConfigManager()
        assert cm.get("slideshow.duration") == 5.0
        assert cm.get("nonexistent.key") is None
        assert cm.get("nonexistent.key", "fallback") == "fallback"

    def test_set_dotted_key(self):
        cm = ConfigManager()
        cm.set("ui.default_zoom", "fill_canvas")
        assert cm.get("ui.default_zoom") == "fill_canvas"

    def test_set_creates_nested_keys(self):
        cm = ConfigManager()
        cm.set("new.nested.key", "value")
        assert cm.get("new.nested.key") == "value"

    def test_save_and_load(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        cm = ConfigManager()
        cm.set("ui.theme", "light")
        cm.save(config_path)

        cm2 = ConfigManager(config_path)
        assert cm2.get("ui.theme") == "light"
        # Defaults should still be present
        assert cm2.get("slideshow.duration") == 5.0

    def test_load_merges_with_defaults(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("ui:\n  theme: light\n")

        cm = ConfigManager(config_path)
        assert cm.get("ui.theme") == "light"
        assert cm.get("ui.default_zoom") == "fit_to_canvas"
        assert cm.get("database.path") == ".photo_manager.db"

    def test_reset(self):
        cm = ConfigManager()
        cm.set("ui.theme", "light")
        cm.reset()
        assert cm.get("ui.theme") == "dark"

    def test_no_path_raises(self):
        cm = ConfigManager()
        with pytest.raises(ValueError):
            cm.load()
        with pytest.raises(ValueError):
            cm.save()
