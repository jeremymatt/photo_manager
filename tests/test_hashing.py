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
        assert len(hashes.phash_180) > 0
        assert len(hashes.phash_270) > 0
        assert len(hashes.dhash_0) > 0
        assert len(hashes.dhash_90) > 0
        assert len(hashes.dhash_180) > 0
        assert len(hashes.dhash_270) > 0
        assert len(hashes.phash_hmirror) > 0
        assert len(hashes.dhash_hmirror) > 0

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

    def test_correlated_rotation_no_false_positive(self, db_with_hashes):
        """pHash match at 0° but dHash match only at 90° should NOT be a dup."""
        # img1 and img3 have pHash matching at 0°-0° but dHash NOT matching
        # at 0°-0° (only at 90°-90°).  With correlated rotation pairs,
        # this should NOT be detected as a duplicate.
        img_a = ImageRecord(
            filepath="corr_a.jpg", filename="corr_a.jpg",
            phash_0="abcdef1234567890", phash_90="1111111111111111",
            phash_180="2222222222222222", phash_270="3333333333333333",
            dhash_0="0000000000000000", dhash_90="ffffffffffffffff",
            dhash_180="4444444444444444", dhash_270="5555555555555555",
            file_size=1000,
        )
        img_b = ImageRecord(
            filepath="corr_b.jpg", filename="corr_b.jpg",
            # pHash matches img_a at 0°
            phash_0="abcdef1234567890", phash_90="6666666666666666",
            phash_180="7777777777777777", phash_270="8888888888888888",
            # dHash matches img_a only at 90° (not at 0° where pHash matches)
            dhash_0="9999999999999999", dhash_90="ffffffffffffffff",
            dhash_180="aaaaaaaaaaaaaaaa", dhash_270="bbbbbbbbbbbbbbbb",
            file_size=1000,
        )
        db_with_hashes.add_image(img_a)
        db_with_hashes.add_image(img_b)
        detector = DuplicateDetector(db_with_hashes, threshold=0)
        groups = detector.find_duplicates()
        # Should NOT be grouped (pHash matches at 0°-0° but dHash doesn't)
        corr_ids = {
            db_with_hashes.get_image_by_path("corr_a.jpg").id,
            db_with_hashes.get_image_by_path("corr_b.jpg").id,
        }
        for group in groups:
            assert not corr_ids.issubset(set(group)), \
                "False positive: pHash/dHash matched at different rotations"

    def test_rotation_aware_duplicate(self, db_with_hashes):
        """Images matching at a non-zero rotation should be detected."""
        img_x = ImageRecord(
            filepath="rot_x.jpg", filename="rot_x.jpg",
            phash_0="1111111111111111", phash_90="2222222222222222",
            phash_180="3333333333333333", phash_270="aaaa000000000000",
            dhash_0="4444444444444444", dhash_90="5555555555555555",
            dhash_180="6666666666666666", dhash_270="bbbb000000000000",
            file_size=1000,
        )
        img_y = ImageRecord(
            filepath="rot_y.jpg", filename="rot_y.jpg",
            # Matches img_x at img_x's 270° vs img_y's 0°
            phash_0="aaaa000000000000", phash_90="cccccccccccccccc",
            phash_180="dddddddddddddddd", phash_270="eeeeeeeeeeeeeeee",
            dhash_0="bbbb000000000000", dhash_90="ffffffffffffffff",
            dhash_180="0000000000000001", dhash_270="0000000000000002",
            file_size=1000,
        )
        db_with_hashes.add_image(img_x)
        db_with_hashes.add_image(img_y)
        detector = DuplicateDetector(db_with_hashes, threshold=0)
        groups = detector.find_duplicates()
        rot_ids = {
            db_with_hashes.get_image_by_path("rot_x.jpg").id,
            db_with_hashes.get_image_by_path("rot_y.jpg").id,
        }
        found = any(rot_ids.issubset(set(g)) for g in groups)
        assert found, "Should detect duplicates at different rotations"

    def test_mirror_duplicate_detection(self, db_with_hashes):
        """Mirrored image should be detected as duplicate via mirror hashes."""
        img_orig = ImageRecord(
            filepath="mirror_orig.jpg", filename="mirror_orig.jpg",
            phash_0="1111111111111111", phash_90="2222222222222222",
            phash_180="3333333333333333", phash_270="4444444444444444",
            dhash_0="5555555555555555", dhash_90="6666666666666666",
            dhash_180="7777777777777777", dhash_270="8888888888888888",
            # Mirror hash matches img_flip's rotation 0° hashes
            phash_hmirror="aaaa000000000000",
            dhash_hmirror="bbbb000000000000",
            file_size=1000,
        )
        img_flip = ImageRecord(
            filepath="mirror_flip.jpg", filename="mirror_flip.jpg",
            # Rotation hashes are completely different from img_orig
            phash_0="aaaa000000000000", phash_90="cccccccccccccccc",
            phash_180="dddddddddddddddd", phash_270="eeeeeeeeeeeeeeee",
            dhash_0="bbbb000000000000", dhash_90="ffffffffffffffff",
            dhash_180="0000000000000001", dhash_270="0000000000000002",
            phash_hmirror="1111111111111111",
            dhash_hmirror="5555555555555555",
            file_size=1000,
        )
        db_with_hashes.add_image(img_orig)
        db_with_hashes.add_image(img_flip)
        detector = DuplicateDetector(db_with_hashes, threshold=0)
        groups = detector.find_duplicates()
        mirror_ids = {
            db_with_hashes.get_image_by_path("mirror_orig.jpg").id,
            db_with_hashes.get_image_by_path("mirror_flip.jpg").id,
        }
        found = any(mirror_ids.issubset(set(g)) for g in groups)
        assert found, "Should detect mirrored images as duplicates"

    def test_mirror_no_false_positive(self, db_with_hashes):
        """Non-mirrored images with different mirror hashes should not match."""
        img_a = ImageRecord(
            filepath="nomirror_a.jpg", filename="nomirror_a.jpg",
            phash_0="1111111111111111", phash_90="2222222222222222",
            phash_180="3333333333333333", phash_270="4444444444444444",
            dhash_0="5555555555555555", dhash_90="6666666666666666",
            dhash_180="7777777777777777", dhash_270="8888888888888888",
            phash_hmirror="aaaa000000000000",
            dhash_hmirror="bbbb000000000000",
            file_size=1000,
        )
        img_b = ImageRecord(
            filepath="nomirror_b.jpg", filename="nomirror_b.jpg",
            phash_0="ff11111111111111", phash_90="ff22222222222222",
            phash_180="ff33333333333333", phash_270="ff44444444444444",
            dhash_0="ff55555555555555", dhash_90="ff66666666666666",
            dhash_180="ff77777777777777", dhash_270="ff88888888888888",
            phash_hmirror="ffaa000000000000",
            dhash_hmirror="ffbb000000000000",
            file_size=1000,
        )
        db_with_hashes.add_image(img_a)
        db_with_hashes.add_image(img_b)
        detector = DuplicateDetector(db_with_hashes, threshold=0)
        groups = detector.find_duplicates()
        nomirror_ids = {
            db_with_hashes.get_image_by_path("nomirror_a.jpg").id,
            db_with_hashes.get_image_by_path("nomirror_b.jpg").id,
        }
        for group in groups:
            assert not nomirror_ids.issubset(set(group)), \
                "False positive: unrelated images matched via mirror"

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

    def test_threshold_boundary(self, tmp_path):
        """Distance == threshold matches; distance == threshold+1 doesn't."""
        db = DatabaseManager()
        db.create_database(tmp_path / "boundary.db")
        try:
            base = "00" * 8                       # 64 zero bits
            three_bits = f"{0b00000111:02x}" + "00" * 7  # distance 3 from base

            # Pair A vs B: distance 3 in phash AND dhash. Threshold 3 -> match.
            img_a = ImageRecord(
                filepath="ba.jpg", filename="ba.jpg",
                phash_0=base, phash_90=base, phash_180=base, phash_270=base,
                dhash_0=base, dhash_90=base, dhash_180=base, dhash_270=base,
                file_size=1000,
            )
            img_b = ImageRecord(
                filepath="bb.jpg", filename="bb.jpg",
                phash_0=three_bits, phash_90=three_bits,
                phash_180=three_bits, phash_270=three_bits,
                dhash_0=three_bits, dhash_90=three_bits,
                dhash_180=three_bits, dhash_270=three_bits,
                file_size=900,
            )
            db.add_image(img_a)
            db.add_image(img_b)

            assert len(DuplicateDetector(db, threshold=3).find_duplicates()) == 1
            assert DuplicateDetector(db, threshold=2).find_duplicates() == []
        finally:
            db.close()

    def test_large_n_finds_known_duplicate(self, tmp_path):
        """BK-tree pruning must not drop a known duplicate buried among noise."""
        import random

        db = DatabaseManager()
        db.create_database(tmp_path / "large.db")
        try:
            rng = random.Random(42)
            # 200 noise images with random distinct hashes
            for i in range(200):
                random_hash = f"{rng.randrange(1 << 64):016x}"
                ph = random_hash
                dh = f"{rng.randrange(1 << 64):016x}"
                db.add_image(ImageRecord(
                    filepath=f"n{i}.jpg", filename=f"n{i}.jpg",
                    phash_0=ph, phash_90=ph, phash_180=ph, phash_270=ph,
                    dhash_0=dh, dhash_90=dh, dhash_180=dh, dhash_270=dh,
                    file_size=1000 + i,
                ))
            # One known-duplicate pair with identical hashes
            dup_ph = "deadbeefcafef00d"
            dup_dh = "0123456789abcdef"
            for tag, size in [("dup_a", 5000), ("dup_b", 4000)]:
                db.add_image(ImageRecord(
                    filepath=f"{tag}.jpg", filename=f"{tag}.jpg",
                    phash_0=dup_ph, phash_90=dup_ph,
                    phash_180=dup_ph, phash_270=dup_ph,
                    dhash_0=dup_dh, dhash_90=dup_dh,
                    dhash_180=dup_dh, dhash_270=dup_dh,
                    file_size=size,
                ))

            groups = DuplicateDetector(db, threshold=10).find_duplicates()
            dup_a_id = db.get_image_by_path("dup_a.jpg").id
            dup_b_id = db.get_image_by_path("dup_b.jpg").id
            assert len(groups) == 1
            assert set(groups[0]) == {dup_a_id, dup_b_id}
            # Larger file size first
            assert groups[0][0] == dup_a_id
        finally:
            db.close()
