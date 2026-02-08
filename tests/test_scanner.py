"""Tests for EXIF extraction, datetime parsing, tag templates, and directory scanner."""

import shutil
from datetime import datetime
from pathlib import Path

import pytest

from photo_manager.db.manager import DatabaseManager
from photo_manager.scanner.datetime_parser import (
    parse_datetime,
    _parse_from_filename,
    _parse_from_path,
)
from photo_manager.scanner.exif import ExifData, extract_exif
from photo_manager.scanner.scanner import DirectoryScanner
from photo_manager.scanner.tag_template import (
    parse_template,
    match_filepath,
    validate_template,
)


# Use the project's test_photos directory
TEST_PHOTOS = Path(__file__).parent.parent / "test_photos"


class TestExifExtraction:
    def test_extract_from_jpg(self):
        jpg_files = list(TEST_PHOTOS.rglob("*.jpg"))
        if not jpg_files:
            pytest.skip("No JPG test files found")
        exif = extract_exif(jpg_files[0])
        assert exif.width is not None
        assert exif.height is not None
        assert exif.width > 0
        assert exif.height > 0

    def test_extract_from_png(self):
        png_files = list(TEST_PHOTOS.rglob("*.png"))
        if not png_files:
            pytest.skip("No PNG test files found")
        exif = extract_exif(png_files[0])
        assert exif.width is not None
        assert exif.height is not None

    def test_extract_from_webp(self):
        webp_files = list(TEST_PHOTOS.rglob("*.webp"))
        if not webp_files:
            pytest.skip("No WebP test files found")
        exif = extract_exif(webp_files[0])
        assert exif.width is not None

    def test_extract_from_gif(self):
        gif_files = list(TEST_PHOTOS.rglob("*.gif"))
        if not gif_files:
            pytest.skip("No GIF test files found")
        exif = extract_exif(gif_files[0])
        assert exif.width is not None


class TestDatetimeParsing:
    def test_parse_from_filename_full(self):
        dt = _parse_from_filename("2019-07-04_15-30-24.jpg")
        assert dt is not None
        assert dt.year == 2019
        assert dt.month == 7
        assert dt.day == 4
        assert dt.hour == 15
        assert dt.minute == 30

    def test_parse_from_filename_img_format(self):
        dt = _parse_from_filename("IMG_20190704_153024.jpg")
        assert dt is not None
        assert dt.year == 2019
        assert dt.month == 7

    def test_parse_from_filename_compact(self):
        dt = _parse_from_filename("20190704_153024.jpg")
        assert dt is not None
        assert dt.year == 2019

    def test_parse_from_filename_date_only(self):
        dt = _parse_from_filename("2019-07-04.jpg")
        assert dt is not None
        assert dt.year == 2019
        assert dt.month == 7
        assert dt.day == 4
        assert dt.hour == 0

    def test_parse_from_filename_no_date(self):
        dt = _parse_from_filename("sunset_photo.jpg")
        assert dt is None

    def test_parse_from_path_year(self):
        dt = _parse_from_path(Path("photos/2019/summer/pic.jpg"))
        assert dt is not None
        assert dt.year == 2019

    def test_parse_from_path_no_year(self):
        dt = _parse_from_path(Path("photos/summer/pic.jpg"))
        assert dt is None

    def test_priority_exif_first(self):
        exif = ExifData(datetime_original=datetime(2020, 6, 15, 10, 30, 0))
        dt = parse_datetime("2019-07-04_pic.jpg", exif)
        assert dt.year == 2020  # EXIF takes priority

    def test_priority_filename_over_path(self):
        dt = parse_datetime(
            Path("photos/2018/2019-07-04_pic.jpg"), None
        )
        assert dt is not None
        assert dt.year == 2019  # Filename takes priority over path


class TestTagTemplate:
    def test_parse_simple_template(self):
        t = parse_template("./{datetime.year}/{event.vacation}/*")
        assert len(t.segments) == 3
        assert t.segments[0].tag_path == "datetime.year"
        assert t.segments[1].tag_path == "event.vacation"
        assert t.segments[2].tag_path is None  # wildcard

    def test_match_filepath(self):
        t = parse_template("./{datetime.year}/{event.vacation}/*")
        result = t.match("2019/Lake/photo.jpg")
        assert result is not None
        assert result["datetime.year"] == "2019"
        assert result["event.vacation"] == "Lake"

    def test_match_with_filename_capture(self):
        t = parse_template("./{datetime.year}/{event.vacation}/{person}.*")
        result = t.match("2019/Lake/Alice.jpg")
        assert result is not None
        assert result["person"] == "Alice"

    def test_no_match_wrong_depth(self):
        t = parse_template("./{datetime.year}/*")
        result = t.match("2019/a/b/photo.jpg")
        assert result is None

    def test_match_filepath_multiple_templates(self):
        templates = [
            parse_template("./{datetime.year}/{event.vacation}/*"),
            parse_template("./{datetime.year}/*"),
        ]
        result = match_filepath("2019/Lake/photo.jpg", templates)
        assert result["datetime.year"] == "2019"
        assert result["event.vacation"] == "Lake"

    def test_validate_template(self, tmp_path):
        db = DatabaseManager()
        db.create_database(tmp_path / "test.db")
        t = parse_template("./{datetime.year}/{nonexistent.tag}/*")
        warnings = validate_template(t, db)
        assert len(warnings) > 0
        assert "nonexistent" in warnings[0]
        db.close()


class TestDirectoryScanner:
    @pytest.fixture
    def scanner_db(self, tmp_path):
        db_path = tmp_path / "scan_test.db"
        db = DatabaseManager()
        db.create_database(db_path)
        yield db
        db.close()

    def test_scan_test_photos(self, scanner_db):
        if not TEST_PHOTOS.exists():
            pytest.skip("test_photos directory not found")

        scanner = DirectoryScanner(scanner_db)
        result = scanner.scan_directory(TEST_PHOTOS)

        assert result.total_found > 0
        assert result.added > 0
        assert result.errors == 0

        # Verify images in database
        count = scanner_db.get_image_count()
        assert count == result.added

    def test_scan_skips_already_added(self, scanner_db):
        if not TEST_PHOTOS.exists():
            pytest.skip("test_photos directory not found")

        scanner = DirectoryScanner(scanner_db)
        result1 = scanner.scan_directory(TEST_PHOTOS)
        result2 = scanner.scan_directory(TEST_PHOTOS)

        assert result2.added == 0
        assert result2.skipped == result1.added

    def test_scan_extracts_dimensions(self, scanner_db):
        if not TEST_PHOTOS.exists():
            pytest.skip("test_photos directory not found")

        scanner = DirectoryScanner(scanner_db)
        scanner.scan_directory(TEST_PHOTOS)

        images = scanner_db.get_all_images()
        assert len(images) > 0
        for img in images:
            assert img.width is not None and img.width > 0
            assert img.height is not None and img.height > 0
