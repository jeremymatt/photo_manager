"""Tests for Phase 3a: organizer components."""

import tempfile
from pathlib import Path

import pytest

from photo_manager.config.config import ConfigManager
from photo_manager.db.manager import DatabaseManager
from photo_manager.scanner.tag_template import (
    load_yaml_template,
    load_template_auto,
    _resolve_back_reference,
    _parse_yaml_pattern,
    TemplateOptions,
)


TEST_PHOTOS = Path(__file__).parent.parent / "test_photos"


# --- YAML Template Tests ---

class TestYAMLTemplate:
    def test_load_yaml_template(self):
        """Test loading the actual load_template.yaml from test_photos."""
        yaml_path = TEST_PHOTOS / "load_template.yaml"
        if not yaml_path.exists():
            pytest.skip("No load_template.yaml in test_photos")
        tmpl = load_yaml_template(str(yaml_path))
        assert tmpl.raw_template == "{scene}/*.*"
        assert tmpl.options.case_insensitive is True
        assert tmpl.options.on_mismatch == "tag_auto_tag_errors"
        assert "scene" in tmpl.tag_mapping
        assert tmpl.tag_mapping["scene"] == "{scene}"

    def test_yaml_template_match(self):
        yaml_path = TEST_PHOTOS / "load_template.yaml"
        if not yaml_path.exists():
            pytest.skip("No load_template.yaml in test_photos")
        tmpl = load_yaml_template(str(yaml_path))
        result = tmpl.match("landscape/photo1.jpg")
        assert result is not None
        assert result["scene"] == "landscape"

    def test_yaml_template_no_match(self):
        yaml_path = TEST_PHOTOS / "load_template.yaml"
        if not yaml_path.exists():
            pytest.skip("No load_template.yaml in test_photos")
        tmpl = load_yaml_template(str(yaml_path))
        # Too many segments — shouldn't match
        result = tmpl.match("a/b/c/photo.jpg")
        assert result is None

    def test_parse_yaml_pattern_simple(self):
        segments = _parse_yaml_pattern("{scene}/{filename}.{ext}")
        assert len(segments) == 2
        assert segments[0].tag_path == "scene"
        assert segments[0].is_filename is False
        assert segments[1].tag_path == "filename"
        assert segments[1].is_filename is True

    def test_parse_yaml_pattern_wildcard(self):
        segments = _parse_yaml_pattern("{year}/*")
        assert len(segments) == 2
        assert segments[0].tag_path == "year"
        assert segments[1].tag_path is None
        assert segments[1].is_filename is True

    def test_resolve_back_reference(self):
        captures = {"scene": "landscape", "filename": "photo1"}
        assert _resolve_back_reference("{scene}", captures) == "landscape"
        assert _resolve_back_reference("{filename}", captures) == "photo1"
        assert _resolve_back_reference("{missing}", captures) is None
        assert _resolve_back_reference("literal_value", captures) == "literal_value"

    def test_load_yaml_template_invalid(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("not_a_dict")
            f.flush()
            with pytest.raises(ValueError, match="expected dict"):
                load_yaml_template(f.name)

    def test_load_yaml_template_missing_pattern(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("version: 1\ntags:\n  scene: test\n")
            f.flush()
            with pytest.raises(ValueError, match="missing 'pattern'"):
                load_yaml_template(f.name)

    def test_template_options_defaults(self):
        opts = TemplateOptions()
        assert opts.case_insensitive is False
        assert opts.require_full_match is True
        assert opts.on_mismatch == "skip_file"


class TestLoadTemplateAuto:
    def test_auto_detects_yaml(self):
        templates = load_template_auto(str(TEST_PHOTOS))
        # test_photos has load_template.yaml
        yaml_path = TEST_PHOTOS / "load_template.yaml"
        if yaml_path.exists():
            assert len(templates) == 1
            assert templates[0].tag_mapping  # YAML templates have tag_mapping

    def test_auto_empty_directory(self, tmp_path):
        templates = load_template_auto(str(tmp_path))
        assert templates == []

    def test_auto_txt_fallback(self, tmp_path):
        (tmp_path / "load_template.txt").write_text(
            "{datetime.year}/{person}.*\n"
        )
        templates = load_template_auto(str(tmp_path))
        assert len(templates) == 1
        assert not templates[0].tag_mapping  # txt templates have no tag_mapping

    def test_yaml_preferred_over_txt(self, tmp_path):
        (tmp_path / "load_template.txt").write_text("{year}/*\n")
        (tmp_path / "load_template.yaml").write_text(
            'version: 1\npattern: "{scene}/{filename}.{ext}"\n'
            "tags:\n  scene: \"{scene}\"\n"
        )
        templates = load_template_auto(str(tmp_path))
        assert len(templates) == 1
        assert templates[0].tag_mapping  # Got the YAML one


# --- ImageSource Tests ---

class TestImageSource:
    def _create_db_with_images(self, tmp_path, count=5):
        """Helper to create a DB with test images."""
        from photo_manager.db.manager import DatabaseManager
        from photo_manager.db.models import ImageRecord

        db_path = tmp_path / "test.db"
        db = DatabaseManager()
        db.create_database(db_path)

        for i in range(count):
            record = ImageRecord(
                filepath=f"photos/img_{i:03d}.jpg",
                filename=f"img_{i:03d}.jpg",
            )
            db.add_image(record)

        return db

    def test_total_count(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 5)
        source = ImageSource(db)
        assert source.total == 5

    def test_get_record(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 3)
        source = ImageSource(db)
        rec = source.get_record(0)
        assert rec is not None
        assert rec.filename == "img_000.jpg"

    def test_get_record_out_of_bounds(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 3)
        source = ImageSource(db)
        assert source.get_record(10) is None
        assert source.get_record(-1) is None

    def test_get_filepath_resolves(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 1)
        source = ImageSource(db)
        fp = source.get_filepath(0)
        assert "photos" in fp
        assert "img_000.jpg" in fp
        # Should be absolute
        assert Path(fp).is_absolute()

    def test_get_file_list(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 3)
        source = ImageSource(db)
        files = source.get_file_list()
        assert len(files) == 3

    def test_refresh(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource
        from photo_manager.db.models import ImageRecord

        db = self._create_db_with_images(tmp_path, 2)
        source = ImageSource(db)
        assert source.total == 2

        # Add another image directly to DB
        db.add_image(ImageRecord(filepath="new.jpg", filename="new.jpg"))
        source.refresh()
        assert source.total == 3

    def test_clear_query(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 3)
        source = ImageSource(db)
        assert source.query_expression is None
        source.clear_query()
        assert source.total == 3
        assert source.query_expression is None


# --- ThumbnailCache Tests (using mocks to avoid QApplication requirement) ---

class TestThumbnailCache:
    def test_put_and_get(self):
        from unittest.mock import MagicMock
        from photo_manager.organizer.thumbnail_worker import ThumbnailCache

        cache = ThumbnailCache(max_count=10)
        pm = MagicMock()
        cache.put(0, pm)
        assert cache.get(0) is pm
        assert cache.get(1) is None

    def test_eviction(self):
        from unittest.mock import MagicMock
        from photo_manager.organizer.thumbnail_worker import ThumbnailCache

        cache = ThumbnailCache(max_count=3)
        for i in range(5):
            cache.put(i, MagicMock())
        assert len(cache) == 3
        # Oldest entries (0, 1) should be evicted
        assert cache.get(0) is None
        assert cache.get(1) is None
        assert cache.get(4) is not None

    def test_clear(self):
        from unittest.mock import MagicMock
        from photo_manager.organizer.thumbnail_worker import ThumbnailCache

        cache = ThumbnailCache()
        cache.put(0, MagicMock())
        cache.clear()
        assert len(cache) == 0

    def test_lru_ordering(self):
        from unittest.mock import MagicMock
        from photo_manager.organizer.thumbnail_worker import ThumbnailCache

        cache = ThumbnailCache(max_count=3)
        for i in range(3):
            cache.put(i, MagicMock())
        # Access index 0 to make it most recent
        cache.get(0)
        # Adding a new item should evict index 1 (least recently used)
        cache.put(3, MagicMock())
        assert cache.get(0) is not None  # Still alive (was accessed)
        assert cache.get(1) is None      # Evicted
        assert cache.get(2) is not None
        assert cache.get(3) is not None


# --- OrganizerKeyHandler Tests (no QApplication needed) ---

class TestOrganizerKeyHandler:
    def test_key_map_coverage(self):
        """Test the key maps have expected entries."""
        from photo_manager.organizer.organizer_key_handler import (
            _SINGLE_KEY_MAP,
            _GRID_KEY_MAP,
            OrganizerAction,
        )

        # Single mode should have nav keys
        single_actions = set(_SINGLE_KEY_MAP.values())
        assert OrganizerAction.NEXT_IMAGE in single_actions
        assert OrganizerAction.PREV_IMAGE in single_actions
        assert OrganizerAction.TOGGLE_VIEW in single_actions
        assert OrganizerAction.QUIT in single_actions
        assert OrganizerAction.IMPORT_DIRECTORY in single_actions

        # Grid mode should NOT have nav keys but should have view toggle
        grid_actions = set(_GRID_KEY_MAP.values())
        assert OrganizerAction.NEXT_IMAGE not in grid_actions
        assert OrganizerAction.TOGGLE_VIEW in grid_actions
        assert OrganizerAction.QUIT in grid_actions
        assert OrganizerAction.IMPORT_DIRECTORY in grid_actions

    def test_grid_mode_property(self):
        from photo_manager.organizer.organizer_key_handler import (
            OrganizerKeyHandler,
        )
        handler = OrganizerKeyHandler()
        assert handler.grid_mode is True
        handler.grid_mode = False
        assert handler.grid_mode is False


# --- App ArgParser Tests ---

class TestOrganizerArgParser:
    def test_basic(self):
        from photo_manager.organizer.app import parse_args
        args = parse_args([])
        assert args.db_path is None
        assert args.db is None
        assert args.import_dir is None
        assert args.view is None

    def test_positional_db_path(self):
        from photo_manager.organizer.app import parse_args
        args = parse_args(["photos.db"])
        assert args.db_path == "photos.db"

    def test_db_flag(self):
        from photo_manager.organizer.app import parse_args
        args = parse_args(["--db", "photos.db"])
        assert args.db == "photos.db"

    def test_import_dir(self):
        from photo_manager.organizer.app import parse_args
        args = parse_args(["--import", "/photos"])
        assert args.import_dir == "/photos"

    def test_view_mode(self):
        from photo_manager.organizer.app import parse_args
        args = parse_args(["--view", "single"])
        assert args.view == "single"

    def test_fullscreen(self):
        from photo_manager.organizer.app import parse_args
        args = parse_args(["--fullscreen"])
        assert args.fullscreen is True

    def test_windowed(self):
        from photo_manager.organizer.app import parse_args
        args = parse_args(["--windowed"])
        assert args.windowed is True


# --- Config Extensions Tests ---

class TestOrganizerTagActions:
    def test_edit_tags_action_in_key_maps(self):
        """Verify tag management actions exist in both key maps."""
        from photo_manager.organizer.organizer_key_handler import (
            _SINGLE_KEY_MAP,
            _GRID_KEY_MAP,
            OrganizerAction,
        )

        single_actions = set(_SINGLE_KEY_MAP.values())
        grid_actions = set(_GRID_KEY_MAP.values())

        for action in (
            OrganizerAction.EDIT_TAGS,
            OrganizerAction.TOGGLE_FAVORITE,
            OrganizerAction.TOGGLE_DELETE,
            OrganizerAction.TOGGLE_REVIEWED,
        ):
            assert action in single_actions, f"{action} missing from single key map"
            assert action in grid_actions, f"{action} missing from grid key map"

    def test_custom_tag_keybindings(self):
        """Verify config-driven custom keybindings are loaded."""
        from photo_manager.organizer.organizer_key_handler import (
            OrganizerKeyHandler,
            _SINGLE_KEY_MAP,
            _GRID_KEY_MAP,
            OrganizerAction,
        )
        from PyQt6.QtCore import Qt

        config = ConfigManager()
        config.set("organizer.tag_keybindings", {"Ctrl+1": "person.Alice"})

        handler = OrganizerKeyHandler()
        handler.load_custom_bindings(config)

        key_tuple = (Qt.Key.Key_1, frozenset({Qt.KeyboardModifier.ControlModifier}))
        assert _SINGLE_KEY_MAP.get(key_tuple) == OrganizerAction.TOGGLE_CUSTOM_TAG
        assert _GRID_KEY_MAP.get(key_tuple) == OrganizerAction.TOGGLE_CUSTOM_TAG
        assert handler._custom_tag_bindings[key_tuple] == "person.Alice"

        # Clean up to avoid polluting other tests
        _SINGLE_KEY_MAP.pop(key_tuple, None)
        _GRID_KEY_MAP.pop(key_tuple, None)

    def test_tag_keybindings_config_default(self):
        """Verify tag_keybindings default exists in config."""
        cm = ConfigManager()
        assert cm.get("organizer.tag_keybindings") == {}


class TestConfigOrganizer:
    def test_organizer_defaults(self):
        cm = ConfigManager()
        assert cm.get("organizer.grid_columns") == 5
        assert cm.get("organizer.default_view") == "grid"
        assert cm.get("organizer.thumbnail_cache_count") == 500
        assert cm.get("organizer.last_db_path") is None
