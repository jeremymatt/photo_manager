"""Tests for the export engine."""

import shutil
from pathlib import Path

import pytest

from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import ImageRecord
from photo_manager.export.exporter import ExportEngine, parse_export_template


TEST_PHOTOS = Path(__file__).parent.parent / "test_photos"


class TestExportTemplateParsing:
    def test_parse_simple(self):
        segments = parse_export_template("{tag.datetime.year}/{tag.event>}")
        assert len(segments) == 2
        assert segments[0].tag_path == "datetime.year"
        assert segments[0].expand is False
        assert segments[1].tag_path == "event"
        assert segments[1].expand is True

    def test_parse_with_root_prefix(self):
        segments = parse_export_template(
            "ROOT_EXPORT_DIR/{tag.datetime.year}/{tag.event}"
        )
        assert len(segments) == 2
        assert segments[0].tag_path == "datetime.year"

    def test_parse_literal_segment(self):
        segments = parse_export_template("photos/{tag.datetime.year}")
        assert len(segments) == 2
        assert segments[0].literal == "photos"
        assert segments[1].tag_path == "datetime.year"

    def test_parse_no_expand(self):
        segments = parse_export_template("{tag.datetime.year}/{tag.event}")
        assert segments[1].expand is False


class TestExportEngine:
    @pytest.fixture
    def export_setup(self, tmp_path):
        """Set up a DB with images and a source directory."""
        # Create source images
        src_dir = tmp_path / "source"
        src_dir.mkdir()

        # Copy a test photo if available
        jpg_files = list(TEST_PHOTOS.rglob("*.jpg")) if TEST_PHOTOS.exists() else []
        if not jpg_files:
            pytest.skip("No test photos available")

        # Copy first test photo as multiple "images"
        for name in ["photo1.jpg", "photo2.jpg", "photo3.jpg"]:
            shutil.copy2(str(jpg_files[0]), str(src_dir / name))

        # Create database
        db_path = tmp_path / ".photo_manager.db"
        db = DatabaseManager()
        db.create_database(db_path)

        # Add images to database
        id1 = db.add_image(ImageRecord(
            filepath="source/photo1.jpg", filename="photo1.jpg",
            year=2019, file_size=1000,
        ))
        id2 = db.add_image(ImageRecord(
            filepath="source/photo2.jpg", filename="photo2.jpg",
            year=2020, file_size=2000,
        ))
        id3 = db.add_image(ImageRecord(
            filepath="source/photo3.jpg", filename="photo3.jpg",
            year=2019, file_size=1500,
        ))

        # Tag images
        event_tag = db.resolve_tag_path("event")
        db.set_image_tag(id1, event_tag.id, "birthday")
        db.set_image_tag(id2, event_tag.id, "vacation")
        db.set_image_tag(id3, event_tag.id, "birthday")

        images = db.get_all_images()
        yield db, images, tmp_path
        db.close()

    def test_export_copy(self, export_setup):
        db, images, tmp_path = export_setup
        export_dir = tmp_path / "export"

        engine = ExportEngine(db)
        result = engine.export(
            images, export_dir,
            template="{tag.datetime.year}",
            mode="copy",
        )

        assert result.exported == 3
        assert result.errors == 0
        assert (export_dir / "2019").exists()
        assert (export_dir / "2020").exists()
        # Source files should still exist
        assert (tmp_path / "source" / "photo1.jpg").exists()

    def test_export_with_csv(self, export_setup):
        db, images, tmp_path = export_setup
        export_dir = tmp_path / "export_csv"

        engine = ExportEngine(db)
        engine.export(
            images, export_dir,
            template="{tag.datetime.year}",
            mode="copy",
            export_csv=True,
        )

        csv_path = export_dir / "image_metadata.csv"
        assert csv_path.exists()
        content = csv_path.read_text()
        assert "filepath" in content
        assert "photo1.jpg" in content

    def test_export_dry_run(self, export_setup):
        db, images, tmp_path = export_setup
        export_dir = tmp_path / "export_dry"

        engine = ExportEngine(db)
        result = engine.export(
            images, export_dir,
            template="{tag.datetime.year}",
            mode="copy",
            dry_run=True,
        )

        assert result.exported == 3
        assert not export_dir.exists()

    def test_export_unknown_tag_creates_unknown_dir(self, export_setup):
        db, images, tmp_path = export_setup
        export_dir = tmp_path / "export_unknown"

        # Use a tag that images don't have
        engine = ExportEngine(db)
        result = engine.export(
            images, export_dir,
            template="{tag.location.city}",
            mode="copy",
        )

        assert result.exported == 3
        assert (export_dir / "Unknown").exists()
