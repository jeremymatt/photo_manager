"""Tests for ConfigManager."""

import tempfile
from pathlib import Path

import pytest

from photo_manager.config.config import ConfigManager, DEFAULT_CONFIG, get_db_config_path


class TestConfigManager:
    def test_default_config(self):
        cm = ConfigManager()
        assert cm.get("ui.default_zoom") == "fit_to_canvas"
        assert cm.get("database.path") == ".photo_manager.db"
        assert cm.get("performance.preload_next_images") == 5

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


class TestGetDbConfigPath:
    def test_basic(self):
        p = get_db_config_path("/photos/my_photos.db")
        assert p == Path("/photos/my_photos.config.yaml")

    def test_relative(self):
        p = get_db_config_path("album.db")
        assert p.name == "album.config.yaml"


class TestLayeredConfig:
    def test_load_layered_creates_db_config(self, tmp_path):
        """load_layered creates a config file next to the DB if none exists."""
        db_config = tmp_path / "photos.config.yaml"
        assert not db_config.exists()

        cm = ConfigManager()
        cm.load_layered(db_config_path=db_config)
        assert db_config.exists()
        # Config should be defaults
        assert cm.get("ui.theme") == "dark"

    def test_load_layered_reads_existing_db_config(self, tmp_path):
        """load_layered picks up settings from existing db config."""
        db_config = tmp_path / "photos.config.yaml"
        db_config.write_text("ui:\n  theme: light\n")

        cm = ConfigManager()
        cm.load_layered(db_config_path=db_config)
        assert cm.get("ui.theme") == "light"
        # Other defaults still present
        assert cm.get("slideshow.duration") == 5.0

    def test_cli_config_overrides_db_config(self, tmp_path):
        """CLI config takes priority over db config."""
        db_config = tmp_path / "photos.config.yaml"
        db_config.write_text("ui:\n  theme: light\n")

        cli_config = tmp_path / "cli.yaml"
        cli_config.write_text("ui:\n  theme: solarized\n")

        cm = ConfigManager()
        cm.load_layered(db_config_path=db_config, cli_config_path=cli_config)
        assert cm.get("ui.theme") == "solarized"

    def test_save_session(self, tmp_path):
        """save_session persists to the db config file."""
        db_config = tmp_path / "photos.config.yaml"

        cm = ConfigManager()
        cm.load_layered(db_config_path=db_config)
        cm.set("ui.theme", "custom_theme")
        cm.save_session()

        # Reload and verify
        cm2 = ConfigManager()
        cm2.load_layered(db_config_path=db_config)
        assert cm2.get("ui.theme") == "custom_theme"

    def test_save_session_no_path_is_noop(self):
        """save_session does nothing if no session path set."""
        cm = ConfigManager()
        cm.save_session()  # Should not raise
