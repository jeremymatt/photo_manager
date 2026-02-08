"""Tests for perceptual hashing and duplicate detection."""

from pathlib import Path

import pytest

from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import ImageRecord
from photo_manager.hashing.duplicates import DuplicateDetector
from photo_manager.hashing.hasher import BackgroundHasher, compute_hashes

TEST_PHOTOS = Path(__file__).parent.parent / "test_photos"


class TestImageHasher:
    def test_compute_hashes_jpg(self):
        jpg_files = list(TEST_PHOTOS.rglob("*.jpg"))
        if not jpg_files:
            pytest.skip("No JPG test files found")

        hashes = compute_hashes(jpg_files[0])
        assert hashes is not None
        assert len(hashes.phash_0) > 0
        assert len(hashes.phash_90) > 0
        assert len(hashes.dhash_0) > 0
        assert len(hashes.dhash_90) > 0

    def test_compute_hashes_png(self):
        png_files = list(TEST_PHOTOS.rglob("*.png"))
        if not png_files:
            pytest.skip("No PNG test files found")

        hashes = compute_hashes(png_files[0])
        assert hashes is not None

    def test_compute_hashes_gif(self):
        gif_files = list(TEST_PHOTOS.rglob("*.gif"))
        if not gif_files:
            pytest.skip("No GIF test files found")

        hashes = compute_hashes(gif_files[0])
        assert hashes is not None

    def test_same_image_same_hash(self):
        jpg_files = list(TEST_PHOTOS.rglob("*.jpg"))
        if not jpg_files:
            pytest.skip("No JPG test files found")

        h1 = compute_hashes(jpg_files[0])
        h2 = compute_hashes(jpg_files[0])
        assert h1.phash_0 == h2.phash_0
        assert h1.dhash_0 == h2.dhash_0

    def test_different_images_different_hash(self):
        jpg_files = list(TEST_PHOTOS.rglob("*.jpg"))
        if len(jpg_files) < 2:
            pytest.skip("Need at least 2 JPG test files")

        h1 = compute_hashes(jpg_files[0])
        h2 = compute_hashes(jpg_files[1])
        # At least one hash should differ
        assert h1.phash_0 != h2.phash_0 or h1.dhash_0 != h2.dhash_0


class TestBackgroundHasher:
    def test_background_hashing(self):
        jpg_files = list(TEST_PHOTOS.rglob("*.jpg"))
        if not jpg_files:
            pytest.skip("No JPG test files found")

        hasher = BackgroundHasher(max_workers=2)
        for i, f in enumerate(jpg_files[:3]):
            hasher.submit(i + 1, f)

        results = hasher.get_results()
        assert len(results) == min(3, len(jpg_files))
        for image_id, hashes in results:
            assert hashes is not None
        hasher.shutdown()


class TestDuplicateDetector:
    @pytest.fixture
    def db_with_hashes(self, tmp_path):
        db = DatabaseManager()
        db.create_database(tmp_path / "dup_test.db")

        # Add images with known hashes
        img1 = ImageRecord(
            filepath="a.jpg", filename="a.jpg",
            phash_0="abcdef1234567890", phash_90="1234567890abcdef",
            dhash_0="abcdef1234567890", dhash_90="1234567890abcdef",
            file_size=1000,
        )
        img2 = ImageRecord(
            filepath="b.jpg", filename="b.jpg",
            phash_0="abcdef1234567890", phash_90="1234567890abcdef",
            dhash_0="abcdef1234567890", dhash_90="1234567890abcdef",
            file_size=2000,
        )
        img3 = ImageRecord(
            filepath="c.jpg", filename="c.jpg",
            phash_0="0000000000000000", phash_90="0000000000000000",
            dhash_0="0000000000000000", dhash_90="0000000000000000",
            file_size=500,
        )

        db.add_image(img1)
        db.add_image(img2)
        db.add_image(img3)

        yield db
        db.close()

    def test_find_exact_duplicates(self, db_with_hashes):
        detector = DuplicateDetector(db_with_hashes, threshold=5)
        groups = detector.find_duplicates()

        assert len(groups) == 1
        assert len(groups[0]) == 2
        # Should be sorted by file_size descending
        img1 = db_with_hashes.get_image(groups[0][0])
        img2 = db_with_hashes.get_image(groups[0][1])
        assert img1.file_size >= img2.file_size

    def test_store_duplicate_groups(self, db_with_hashes):
        detector = DuplicateDetector(db_with_hashes, threshold=5)
        groups = detector.find_duplicates()
        group_ids = detector.store_duplicate_groups(groups)

        assert len(group_ids) == 1
        stored_groups = db_with_hashes.get_duplicate_groups()
        assert len(stored_groups) == 1
        assert len(stored_groups[0].members) == 2
