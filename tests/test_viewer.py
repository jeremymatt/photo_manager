"""Tests for the lightweight viewer components.

Note: Tests that require a QApplication are marked and will create one
in headless mode. These test the non-GUI logic of viewer components.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from photo_manager.viewer.image_loader import ImageCache, collect_image_files
from photo_manager.viewer.key_handler import Action, KeyHandler


TEST_PHOTOS = Path(__file__).parent.parent / "test_photos"


class TestCollectImageFiles:
    def test_finds_images(self):
        if not TEST_PHOTOS.exists():
            pytest.skip("test_photos not found")
        files = collect_image_files(TEST_PHOTOS)
        assert len(files) > 0

    def test_finds_all_formats(self):
        if not TEST_PHOTOS.exists():
            pytest.skip("test_photos not found")
        files = collect_image_files(TEST_PHOTOS)
        extensions = {Path(f).suffix.lower() for f in files}
        # Should find at least jpg, png, gif, webp from test photos
        assert ".jpg" in extensions
        assert ".png" in extensions
        assert ".gif" in extensions

    def test_sorted_alphabetically(self):
        if not TEST_PHOTOS.exists():
            pytest.skip("test_photos not found")
        files = collect_image_files(TEST_PHOTOS)
        assert files == sorted(files)

    def test_non_recursive(self):
        if not TEST_PHOTOS.exists():
            pytest.skip("test_photos not found")
        files_recursive = collect_image_files(TEST_PHOTOS, recursive=True)
        files_flat = collect_image_files(TEST_PHOTOS, recursive=False)
        # Non-recursive should find fewer or equal (test_photos has subdirs)
        assert len(files_flat) <= len(files_recursive)


class TestImageCache:
    """Test the LRU image cache (no QApplication needed for basic logic)."""

    def test_put_and_get(self):
        # We can't create real QPixmaps without QApplication,
        # but we can test the cache logic with mocks
        cache = ImageCache(max_size_mb=100)
        # Mock a pixmap with known size
        mock_pm = MagicMock()
        mock_img = MagicMock()
        mock_img.sizeInBytes.return_value = 1024
        mock_img.isNull.return_value = False
        mock_pm.toImage.return_value = mock_img

        cache.put(0, mock_pm)
        assert 0 in cache
        assert cache.get(0) is mock_pm

    def test_cache_miss(self):
        cache = ImageCache(max_size_mb=100)
        assert cache.get(99) is None
        assert 99 not in cache

    def test_clear(self):
        cache = ImageCache(max_size_mb=100)
        mock_pm = MagicMock()
        mock_img = MagicMock()
        mock_img.sizeInBytes.return_value = 1024
        mock_img.isNull.return_value = False
        mock_pm.toImage.return_value = mock_img

        cache.put(0, mock_pm)
        cache.clear()
        assert 0 not in cache


class TestKeyHandler:
    """Test key handler action mapping (no QApplication needed)."""

    def _make_key_event(self, key, modifiers=None):
        """Create a mock QKeyEvent."""
        from unittest.mock import MagicMock
        from PyQt6.QtCore import Qt
        event = MagicMock()
        event.key.return_value = key
        if modifiers is None:
            modifiers = Qt.KeyboardModifier(0)
        event.modifiers.return_value = modifiers
        return event

    def test_right_arrow_next(self):
        from PyQt6.QtCore import Qt
        handler = KeyHandler()
        actions: list[Action] = []
        handler.action_triggered.connect(actions.append)

        event = self._make_key_event(Qt.Key.Key_Right)
        result = handler.handle_key_event(event)
        assert result is True
        assert actions == [Action.NEXT_IMAGE]

    def test_left_arrow_prev(self):
        from PyQt6.QtCore import Qt
        handler = KeyHandler()
        actions: list[Action] = []
        handler.action_triggered.connect(actions.append)

        event = self._make_key_event(Qt.Key.Key_Left)
        handler.handle_key_event(event)
        assert actions == [Action.PREV_IMAGE]

    def test_shift_right_next_folder(self):
        from PyQt6.QtCore import Qt
        handler = KeyHandler()
        actions: list[Action] = []
        handler.action_triggered.connect(actions.append)

        event = self._make_key_event(
            Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier
        )
        handler.handle_key_event(event)
        assert actions == [Action.NEXT_FOLDER]

    def test_escape_quit(self):
        from PyQt6.QtCore import Qt
        handler = KeyHandler()
        actions: list[Action] = []
        handler.action_triggered.connect(actions.append)

        event = self._make_key_event(Qt.Key.Key_Escape)
        handler.handle_key_event(event)
        assert actions == [Action.QUIT]

    def test_ctrl_r_reset(self):
        from PyQt6.QtCore import Qt
        handler = KeyHandler()
        actions: list[Action] = []
        handler.action_triggered.connect(actions.append)

        event = self._make_key_event(
            Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier
        )
        handler.handle_key_event(event)
        assert actions == [Action.RESET_IMAGE]

    def test_f11_fullscreen(self):
        from PyQt6.QtCore import Qt
        handler = KeyHandler()
        actions: list[Action] = []
        handler.action_triggered.connect(actions.append)

        event = self._make_key_event(Qt.Key.Key_F11)
        handler.handle_key_event(event)
        assert actions == [Action.TOGGLE_FULLSCREEN]

    def test_unmapped_key_returns_false(self):
        from PyQt6.QtCore import Qt
        handler = KeyHandler()
        event = self._make_key_event(Qt.Key.Key_A)
        result = handler.handle_key_event(event)
        assert result is False

    def test_alt_m_help(self):
        from PyQt6.QtCore import Qt
        handler = KeyHandler()
        actions: list[Action] = []
        handler.action_triggered.connect(actions.append)

        event = self._make_key_event(
            Qt.Key.Key_M, Qt.KeyboardModifier.AltModifier
        )
        handler.handle_key_event(event)
        assert actions == [Action.TOGGLE_HELP]

    def test_tab_cycle_zoom(self):
        from PyQt6.QtCore import Qt
        handler = KeyHandler()
        actions: list[Action] = []
        handler.action_triggered.connect(actions.append)

        event = self._make_key_event(Qt.Key.Key_Tab)
        handler.handle_key_event(event)
        assert actions == [Action.CYCLE_ZOOM_MODE]

    def test_space_slideshow(self):
        from PyQt6.QtCore import Qt
        handler = KeyHandler()
        actions: list[Action] = []
        handler.action_triggered.connect(actions.append)

        event = self._make_key_event(Qt.Key.Key_Space)
        handler.handle_key_event(event)
        assert actions == [Action.TOGGLE_SLIDESHOW_PAUSE]


class TestAppArgParser:
    """Test CLI argument parsing."""

    def test_basic_path(self):
        from photo_manager.viewer.app import build_parser
        parser = build_parser()
        args = parser.parse_args(["test_photos/"])
        assert args.path == "test_photos/"
        assert args.slideshow is False
        assert args.query is None

    def test_slideshow_flag(self):
        from photo_manager.viewer.app import build_parser
        parser = build_parser()
        args = parser.parse_args(["test_photos/", "--slideshow"])
        assert args.slideshow is True

    def test_query_with_value(self):
        from photo_manager.viewer.app import build_parser
        parser = build_parser()
        args = parser.parse_args(["test.db", "--query", 'tag.person=="Alice"'])
        assert args.query == 'tag.person=="Alice"'

    def test_query_without_value(self):
        from photo_manager.viewer.app import build_parser
        parser = build_parser()
        args = parser.parse_args(["test.db", "--query"])
        assert args.query == ""  # empty string means "open dialog"

    def test_query_not_provided(self):
        from photo_manager.viewer.app import build_parser
        parser = build_parser()
        args = parser.parse_args(["test.db"])
        assert args.query is None  # None means "all images"

    def test_fullscreen_flags(self):
        from photo_manager.viewer.app import build_parser
        parser = build_parser()
        args = parser.parse_args(["photos/", "--fullscreen"])
        assert args.fullscreen is True

        args = parser.parse_args(["photos/", "--windowed"])
        assert args.windowed is True
