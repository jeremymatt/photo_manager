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
        """Verify EDIT_TAGS exists in both key maps."""
        from photo_manager.organizer.organizer_key_handler import (
            _SINGLE_KEY_MAP,
            _GRID_KEY_MAP,
            OrganizerAction,
        )

        single_actions = set(_SINGLE_KEY_MAP.values())
        grid_actions = set(_GRID_KEY_MAP.values())

        assert OrganizerAction.EDIT_TAGS in single_actions
        assert OrganizerAction.EDIT_TAGS in grid_actions

    def test_quick_toggle_bindings_loaded(self):
        """Verify default quick_toggle_bindings are loaded as QUICK_BINDING."""
        from photo_manager.organizer.organizer_key_handler import (
            OrganizerKeyHandler,
            _SINGLE_KEY_MAP,
            _GRID_KEY_MAP,
            OrganizerAction,
        )
        from PyQt6.QtCore import Qt

        config = ConfigManager()
        handler = OrganizerKeyHandler()
        handler.load_all_bindings(config)

        # Default bindings: F, D, R
        f_tuple = (Qt.Key.Key_F, frozenset())
        d_tuple = (Qt.Key.Key_D, frozenset())
        r_tuple = (Qt.Key.Key_R, frozenset())

        assert _SINGLE_KEY_MAP.get(f_tuple) == OrganizerAction.QUICK_BINDING
        assert _SINGLE_KEY_MAP.get(d_tuple) == OrganizerAction.QUICK_BINDING
        assert _SINGLE_KEY_MAP.get(r_tuple) == OrganizerAction.QUICK_BINDING
        assert handler._binding_actions[f_tuple] == ["set_favorite"]
        assert handler._binding_actions[d_tuple] == ["set_to_delete"]
        assert handler._binding_actions[r_tuple] == ["set_reviewed"]

        # Clean up
        for key in [f_tuple, d_tuple, r_tuple]:
            _SINGLE_KEY_MAP.pop(key, None)
            _GRID_KEY_MAP.pop(key, None)

    def test_multi_action_binding(self):
        """Verify a binding can have multiple actions."""
        from photo_manager.organizer.organizer_key_handler import (
            OrganizerKeyHandler,
            _SINGLE_KEY_MAP,
            _GRID_KEY_MAP,
            OrganizerAction,
        )
        from PyQt6.QtCore import Qt

        config = ConfigManager()
        config.set("organizer.quick_toggle_bindings", {
            "/": ["set_reviewed", "next_image"],
        })

        handler = OrganizerKeyHandler()
        handler.load_all_bindings(config)

        slash_tuple = (Qt.Key.Key_Slash, frozenset())
        assert _SINGLE_KEY_MAP.get(slash_tuple) == OrganizerAction.QUICK_BINDING
        assert handler._binding_actions[slash_tuple] == ["set_reviewed", "next_image"]

        # Clean up
        _SINGLE_KEY_MAP.pop(slash_tuple, None)
        _GRID_KEY_MAP.pop(slash_tuple, None)

    def test_legacy_tag_keybindings(self):
        """Verify legacy tag_keybindings are loaded as tag: actions."""
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
        handler.load_all_bindings(config)

        key_tuple = (Qt.Key.Key_1, frozenset({Qt.KeyboardModifier.ControlModifier}))
        assert _SINGLE_KEY_MAP.get(key_tuple) == OrganizerAction.QUICK_BINDING
        assert _GRID_KEY_MAP.get(key_tuple) == OrganizerAction.QUICK_BINDING
        assert handler._binding_actions[key_tuple] == ["tag:person.Alice"]

        # Clean up
        _SINGLE_KEY_MAP.pop(key_tuple, None)
        _GRID_KEY_MAP.pop(key_tuple, None)

    def test_tag_keybindings_config_default(self):
        """Verify tag_keybindings default exists in config."""
        cm = ConfigManager()
        assert cm.get("organizer.tag_keybindings") == {}

    def test_quick_toggle_bindings_config_default(self):
        """Verify quick_toggle_bindings default exists in config."""
        cm = ConfigManager()
        bindings = cm.get("organizer.quick_toggle_bindings")
        assert "F" in bindings
        assert bindings["F"] == ["set_favorite"]


class TestBindingCleanup:
    def test_reload_clears_previous_bindings(self):
        """Verify reloading bindings removes old dynamic keys."""
        from photo_manager.organizer.organizer_key_handler import (
            OrganizerKeyHandler,
            _SINGLE_KEY_MAP,
            _GRID_KEY_MAP,
            OrganizerAction,
        )
        from PyQt6.QtCore import Qt

        handler = OrganizerKeyHandler()

        # Load first set
        config1 = ConfigManager()
        config1.set("organizer.quick_toggle_bindings", {"1": ["set_favorite"]})
        handler.load_all_bindings(config1)
        key1 = (Qt.Key.Key_1, frozenset())
        assert _SINGLE_KEY_MAP.get(key1) == OrganizerAction.QUICK_BINDING

        # Reload with different bindings
        config2 = ConfigManager()
        config2.set("organizer.quick_toggle_bindings", {"2": ["set_reviewed"]})
        handler.load_all_bindings(config2)
        key2 = (Qt.Key.Key_2, frozenset())
        assert key1 not in _SINGLE_KEY_MAP  # Old binding removed
        assert _SINGLE_KEY_MAP.get(key2) == OrganizerAction.QUICK_BINDING

        # Clean up
        _SINGLE_KEY_MAP.pop(key2, None)
        _GRID_KEY_MAP.pop(key2, None)


class TestInfoOverlayBuildText:
    """Test InfoOverlay._build_text logic without QApplication."""

    def _make_overlay(self):
        """Create an InfoOverlay-like object for testing _build_text."""
        from unittest.mock import MagicMock

        class FakeOverlay:
            def __init__(self):
                self._level = 1
                self._index = 0
                self._total = 5
                self._folder = ""
                self._filename = "img.jpg"
                self._zoom_percent = 100
                self._width = 800
                self._height = 600
                self._tags = []

            def cycle_level(self):
                self._level = (self._level % 4) + 1
                return self._level

            # Borrow _build_text from the real class
            from photo_manager.viewer.info_overlay import InfoOverlay
            _build_text = InfoOverlay._build_text

        return FakeOverlay()

    def test_cycle_through_4_levels(self):
        overlay = self._make_overlay()
        assert overlay._level == 1
        overlay.cycle_level()
        assert overlay._level == 2
        overlay.cycle_level()
        assert overlay._level == 3
        overlay.cycle_level()
        assert overlay._level == 4
        overlay.cycle_level()
        assert overlay._level == 1  # wraps

    def test_level_4_build_text_with_tags(self):
        overlay = self._make_overlay()
        overlay._tags = ["person.Alice", "scene.landscape"]
        for _ in range(3):
            overlay.cycle_level()
        assert overlay._level == 4
        text = overlay._build_text()
        assert "person.Alice" in text
        assert "scene.landscape" in text
        assert "\n" in text

    def test_level_3_no_tags(self):
        overlay = self._make_overlay()
        overlay._tags = ["person.Alice"]
        for _ in range(2):
            overlay.cycle_level()
        assert overlay._level == 3
        text = overlay._build_text()
        assert "person.Alice" not in text  # Tags only at level 4

    def test_level_4_no_tags_no_newline(self):
        overlay = self._make_overlay()
        overlay._tags = []
        for _ in range(3):
            overlay.cycle_level()
        text = overlay._build_text()
        assert "\n" not in text  # No tags means no extra lines


class TestNewKeyMapActions:
    """Test that the 6 new actions are in the key maps."""

    def test_single_key_map_has_new_actions(self):
        from photo_manager.organizer.organizer_key_handler import (
            _SINGLE_KEY_MAP,
            OrganizerAction,
        )
        single_actions = set(_SINGLE_KEY_MAP.values())
        assert OrganizerAction.MARK_DELETE in single_actions
        assert OrganizerAction.APPLY_TAGS_TO_FOLDER in single_actions
        assert OrganizerAction.MARK_DELETE_FOLDER in single_actions
        assert OrganizerAction.REVIEW_DELETIONS in single_actions
        assert OrganizerAction.EXECUTE_DELETIONS in single_actions
        assert OrganizerAction.SHOW_TAG_HOTKEYS in single_actions

    def test_grid_key_map_has_delete_actions(self):
        from photo_manager.organizer.organizer_key_handler import (
            _GRID_KEY_MAP,
            OrganizerAction,
        )
        grid_actions = set(_GRID_KEY_MAP.values())
        assert OrganizerAction.MARK_DELETE in grid_actions
        assert OrganizerAction.REVIEW_DELETIONS in grid_actions
        assert OrganizerAction.EXECUTE_DELETIONS in grid_actions
        assert OrganizerAction.SHOW_TAG_HOTKEYS in grid_actions

    def test_key_bindings_for_new_actions(self):
        from photo_manager.organizer.organizer_key_handler import (
            _SINGLE_KEY_MAP,
            OrganizerAction,
        )
        from PyQt6.QtCore import Qt

        assert _SINGLE_KEY_MAP[(Qt.Key.Key_Period, frozenset())] == OrganizerAction.MARK_DELETE
        assert _SINGLE_KEY_MAP[(Qt.Key.Key_V, frozenset({Qt.KeyboardModifier.ControlModifier}))] == OrganizerAction.APPLY_TAGS_TO_FOLDER
        assert _SINGLE_KEY_MAP[(Qt.Key.Key_D, frozenset({Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.AltModifier}))] == OrganizerAction.MARK_DELETE_FOLDER
        assert _SINGLE_KEY_MAP[(Qt.Key.Key_D, frozenset({Qt.KeyboardModifier.AltModifier}))] == OrganizerAction.REVIEW_DELETIONS
        assert _SINGLE_KEY_MAP[(Qt.Key.Key_D, frozenset({Qt.KeyboardModifier.ControlModifier}))] == OrganizerAction.EXECUTE_DELETIONS
        assert _SINGLE_KEY_MAP[(Qt.Key.Key_T, frozenset({Qt.KeyboardModifier.AltModifier, Qt.KeyboardModifier.ShiftModifier}))] == OrganizerAction.SHOW_TAG_HOTKEYS


class TestImageSourceDeleteFilter:
    """Test ImageSource delete filtering."""

    def _create_db_with_images(self, tmp_path, count=5):
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

    def test_delete_filter_off_by_default(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 5)
        source = ImageSource(db)
        assert source.is_filtered is False
        assert source.total == 5

    def test_delete_filter_shows_only_marked(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 5)
        # Mark images 1 and 3 for deletion
        all_images = db.get_all_images()
        all_images[1].to_delete = True
        db.update_image(all_images[1])
        all_images[3].to_delete = True
        db.update_image(all_images[3])

        source = ImageSource(db)
        source.set_delete_filter(True)
        assert source.is_filtered is True
        assert source.total == 2
        # Should return the correct records
        rec0 = source.get_record(0)
        rec1 = source.get_record(1)
        assert rec0 is not None
        assert rec1 is not None
        assert rec0.filename == "img_001.jpg"
        assert rec1.filename == "img_003.jpg"

    def test_delete_filter_off_restores_all(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 5)
        all_images = db.get_all_images()
        all_images[0].to_delete = True
        db.update_image(all_images[0])

        source = ImageSource(db)
        source.set_delete_filter(True)
        assert source.total == 1
        source.set_delete_filter(False)
        assert source.total == 5

    def test_delete_filter_get_filepath(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 3)
        all_images = db.get_all_images()
        all_images[2].to_delete = True
        db.update_image(all_images[2])

        source = ImageSource(db)
        source.set_delete_filter(True)
        assert source.total == 1
        fp = source.get_filepath(0)
        assert "img_002.jpg" in fp

    def test_delete_filter_get_file_list(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 4)
        all_images = db.get_all_images()
        all_images[0].to_delete = True
        all_images[2].to_delete = True
        db.update_image(all_images[0])
        db.update_image(all_images[2])

        source = ImageSource(db)
        source.set_delete_filter(True)
        files = source.get_file_list()
        assert len(files) == 2

    def test_delete_filter_out_of_bounds(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 3)
        all_images = db.get_all_images()
        all_images[1].to_delete = True
        db.update_image(all_images[1])

        source = ImageSource(db)
        source.set_delete_filter(True)
        assert source.total == 1
        assert source.get_record(1) is None
        assert source.get_record(-1) is None


class TestConfigOrganizer:
    def test_organizer_defaults(self):
        cm = ConfigManager()
        assert cm.get("organizer.grid_columns") == 5
        assert cm.get("organizer.default_view") == "grid"
        assert cm.get("organizer.thumbnail_cache_count") == 500
        assert cm.get("organizer.last_db_path") is None


class TestDupKeyMapActions:
    """Test that duplicate management actions are in the key maps."""

    def test_single_key_map_has_dup_actions(self):
        from photo_manager.organizer.organizer_key_handler import (
            _SINGLE_KEY_MAP,
            OrganizerAction,
        )
        single_actions = set(_SINGLE_KEY_MAP.values())
        assert OrganizerAction.DETECT_DUPLICATES in single_actions
        assert OrganizerAction.ENTER_DUP_REVIEW in single_actions
        assert OrganizerAction.TOGGLE_NOT_DUPLICATE in single_actions
        assert OrganizerAction.KEEP_IMAGE in single_actions
        # Shift+Arrow already maps to NEXT_FOLDER/PREV_FOLDER in single map
        # which redirects to dup group nav when in dup mode

    def test_grid_key_map_has_dup_actions(self):
        from photo_manager.organizer.organizer_key_handler import (
            _GRID_KEY_MAP,
            OrganizerAction,
        )
        grid_actions = set(_GRID_KEY_MAP.values())
        assert OrganizerAction.DETECT_DUPLICATES in grid_actions
        assert OrganizerAction.ENTER_DUP_REVIEW in grid_actions
        assert OrganizerAction.TOGGLE_NOT_DUPLICATE in grid_actions
        assert OrganizerAction.KEEP_IMAGE in grid_actions
        # Shift+Arrow maps to NEXT_FOLDER/PREV_FOLDER in grid map too
        assert OrganizerAction.NEXT_FOLDER in grid_actions
        assert OrganizerAction.PREV_FOLDER in grid_actions

    def test_dup_key_bindings(self):
        from photo_manager.organizer.organizer_key_handler import (
            _SINGLE_KEY_MAP,
            _GRID_KEY_MAP,
            OrganizerAction,
        )
        from PyQt6.QtCore import Qt

        assert _SINGLE_KEY_MAP[(Qt.Key.Key_D, frozenset({Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier}))] == OrganizerAction.DETECT_DUPLICATES
        assert _SINGLE_KEY_MAP[(Qt.Key.Key_F3, frozenset())] == OrganizerAction.ENTER_DUP_REVIEW
        assert _SINGLE_KEY_MAP[(Qt.Key.Key_N, frozenset({Qt.KeyboardModifier.ControlModifier}))] == OrganizerAction.TOGGLE_NOT_DUPLICATE
        assert _SINGLE_KEY_MAP[(Qt.Key.Key_K, frozenset({Qt.KeyboardModifier.ControlModifier}))] == OrganizerAction.KEEP_IMAGE
        # Alt+Arrow for folder/dup group nav (reuses NEXT_FOLDER/PREV_FOLDER)
        assert _GRID_KEY_MAP[(Qt.Key.Key_Right, frozenset({Qt.KeyboardModifier.AltModifier}))] == OrganizerAction.NEXT_FOLDER
        assert _GRID_KEY_MAP[(Qt.Key.Key_Left, frozenset({Qt.KeyboardModifier.AltModifier}))] == OrganizerAction.PREV_FOLDER
        # Ctrl+Shift+S for save with rotation (single view only)
        assert _SINGLE_KEY_MAP[(Qt.Key.Key_S, frozenset({Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier}))] == OrganizerAction.SAVE_WITH_ROTATION
        assert (Qt.Key.Key_S, frozenset({Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier})) not in _GRID_KEY_MAP


class TestImageSourceDupFilter:
    """Test ImageSource duplicate group filtering."""

    def _create_db_with_images(self, tmp_path, count=5):
        from photo_manager.db.models import ImageRecord

        db_path = tmp_path / "test.db"
        db = DatabaseManager()
        db.create_database(db_path)

        for i in range(count):
            record = ImageRecord(
                filepath=f"photos/img_{i:03d}.jpg",
                filename=f"img_{i:03d}.jpg",
                file_size=(count - i) * 1000,  # Descending sizes
            )
            db.add_image(record)

        return db

    def test_dup_filter_off_by_default(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 5)
        source = ImageSource(db)
        assert source.is_dup_filtered is False
        assert source.dup_group_count == 0

    def test_dup_filter_no_groups(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 5)
        source = ImageSource(db)
        source.set_dup_filter(True)
        assert source.dup_group_count == 0
        assert source.total == 0  # No groups = no images to show

    def test_dup_filter_with_group(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 5)
        all_images = db.get_all_images()
        # Create a dup group with images 0, 2, 4
        group_ids = [all_images[0].id, all_images[2].id, all_images[4].id]
        db.create_duplicate_group(group_ids)

        source = ImageSource(db)
        source.set_dup_filter(True)
        assert source.dup_group_count == 1
        assert source.current_dup_group_index == 0
        assert source.total == 3

    def test_dup_filter_sorted_by_file_size(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 5)
        all_images = db.get_all_images()
        # Images have descending sizes: img_000=5000, img_001=4000, ...
        # Create group with images 1, 3 (sizes 4000, 2000)
        group_ids = [all_images[1].id, all_images[3].id]
        db.create_duplicate_group(group_ids)

        source = ImageSource(db)
        source.set_dup_filter(True)
        assert source.total == 2
        rec0 = source.get_record(0)
        rec1 = source.get_record(1)
        assert rec0 is not None and rec1 is not None
        # Largest first
        assert rec0.file_size >= rec1.file_size

    def test_dup_filter_multiple_groups(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 6)
        all_images = db.get_all_images()
        db.create_duplicate_group([all_images[0].id, all_images[1].id])
        db.create_duplicate_group([all_images[2].id, all_images[3].id])

        source = ImageSource(db)
        source.set_dup_filter(True)
        assert source.dup_group_count == 2
        assert source.current_dup_group_index == 0
        assert source.total == 2  # First group has 2 images

        # Navigate to second group
        source.set_dup_group(1)
        assert source.current_dup_group_index == 1
        assert source.total == 2  # Second group also has 2

    def test_dup_filter_get_dup_member(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 4)
        all_images = db.get_all_images()
        db.create_duplicate_group([all_images[0].id, all_images[1].id])

        source = ImageSource(db)
        source.set_dup_filter(True)
        member = source.get_dup_member(all_images[0].id)
        assert member is not None
        assert member.image_id == all_images[0].id
        assert member.is_kept is False
        assert member.is_not_duplicate is False

    def test_dup_filter_get_dup_member_not_in_group(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 4)
        all_images = db.get_all_images()
        db.create_duplicate_group([all_images[0].id, all_images[1].id])

        source = ImageSource(db)
        source.set_dup_filter(True)
        # Image 2 is not in any group
        member = source.get_dup_member(all_images[2].id)
        assert member is None

    def test_dup_filter_off_restores_all(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 5)
        all_images = db.get_all_images()
        db.create_duplicate_group([all_images[0].id, all_images[1].id])

        source = ImageSource(db)
        source.set_dup_filter(True)
        assert source.total == 2
        source.set_dup_filter(False)
        assert source.total == 5
        assert source.is_dup_filtered is False

    def test_dup_filter_reload_groups(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 4)
        all_images = db.get_all_images()
        db.create_duplicate_group([all_images[0].id, all_images[1].id])

        source = ImageSource(db)
        source.set_dup_filter(True)
        assert source.dup_group_count == 1

        # Update member flag
        group = source.current_dup_group
        assert group is not None
        db.update_duplicate_member(group.members[0].id, is_kept=True)
        source.reload_dup_groups()

        updated_group = source.current_dup_group
        assert updated_group is not None
        kept = [m for m in updated_group.members if m.is_kept]
        assert len(kept) == 1

    def test_dup_filter_overrides_delete_filter(self, tmp_path):
        from photo_manager.organizer.image_source import ImageSource

        db = self._create_db_with_images(tmp_path, 5)
        all_images = db.get_all_images()
        # Mark images 0, 1 for deletion
        all_images[0].to_delete = True
        all_images[1].to_delete = True
        db.update_image(all_images[0])
        db.update_image(all_images[1])
        # Create dup group with images 2, 3
        db.create_duplicate_group([all_images[2].id, all_images[3].id])

        source = ImageSource(db)
        source.set_delete_filter(True)
        assert source.total == 2  # 2 marked for deletion

        # Dup filter should override
        source.set_dup_filter(True)
        assert source.total == 2  # 2 in dup group, not the delete-marked ones
        rec = source.get_record(0)
        assert rec is not None
        assert rec.to_delete is False  # These are the dup group images
