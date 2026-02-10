"""Duplicate detection using perceptual hashes."""

from __future__ import annotations

import logging
from typing import Callable

import imagehash

from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import ImageRecord

logger = logging.getLogger(__name__)

# Callback: (current_count, total_count)
ProgressCallback = Callable[[int, int], None]


class DuplicateDetector:
    """Detect duplicate images using perceptual hash comparison."""

    def __init__(self, db: DatabaseManager, threshold: int = 10):
        self._db = db
        self._threshold = threshold

    def find_duplicates(
        self,
        progress_callback: ProgressCallback | None = None,
    ) -> list[list[int]]:
        """Find groups of duplicate images in the database.

        Two images are considered duplicates when BOTH their pHash AND dHash
        are within the threshold distance at the SAME rotation pair, checking
        all 16 rotation combinations (4 rotations × 4 rotations).

        Returns a list of groups, where each group is a list of image IDs
        sorted by file_size descending.
        """
        images = self._db.get_all_images()
        # Filter to images that have hashes computed
        hashed = [
            img for img in images
            if img.phash_0 is not None and img.dhash_0 is not None
        ]

        total = len(hashed)
        # Union-Find for grouping
        parent: dict[int, int] = {img.id: img.id for img in hashed}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Compare all pairs
        count = 0
        total_pairs = total * (total - 1) // 2
        for i in range(total):
            for j in range(i + 1, total):
                count += 1
                if progress_callback and count % 1000 == 0:
                    progress_callback(count, total_pairs)

                if self._are_duplicates(hashed[i], hashed[j]):
                    union(hashed[i].id, hashed[j].id)

        # Build groups
        groups: dict[int, list[int]] = {}
        for img in hashed:
            root = find(img.id)
            groups.setdefault(root, []).append(img.id)

        # Filter to groups with 2+ members, sort by file size
        result = []
        for group_ids in groups.values():
            if len(group_ids) < 2:
                continue
            # Sort by file_size descending
            group_images = [
                (img_id, self._get_file_size(img_id, hashed))
                for img_id in group_ids
            ]
            group_images.sort(key=lambda x: x[1] or 0, reverse=True)
            result.append([img_id for img_id, _ in group_images])

        return result

    def store_duplicate_groups(self, groups: list[list[int]]) -> list[int]:
        """Store duplicate groups in the database.

        Returns list of created group IDs.
        """
        group_ids = []
        for image_ids in groups:
            group_id = self._db.create_duplicate_group(image_ids)
            group_ids.append(group_id)
        return group_ids

    def _are_duplicates(self, a: ImageRecord, b: ImageRecord) -> bool:
        """Check if two images are duplicates using rotation-aware hash comparison.

        For each of the 16 rotation pairs (4 rotations of A × 4 rotations of B),
        both pHash AND dHash must be within threshold at the SAME rotation pair.

        Also checks mirror: each image's mirror hash pair is compared against
        the other image's non-mirror rotation pairs.
        """
        # Build paired (phash, dhash) tuples for each rotation
        a_pairs = self._get_hash_pairs(a)
        b_pairs = self._get_hash_pairs(b)

        if not a_pairs or not b_pairs:
            return False

        # Check all rotation combinations — both hashes must match at same pair
        for a_ph, a_dh in a_pairs:
            for b_ph, b_dh in b_pairs:
                if (a_ph - b_ph) <= self._threshold and (a_dh - b_dh) <= self._threshold:
                    return True

        # Check mirror: A's mirror vs B's rotations, and B's mirror vs A's rotations
        a_mirror = self._get_mirror_pair(a)
        b_mirror = self._get_mirror_pair(b)

        if a_mirror:
            for b_ph, b_dh in b_pairs:
                if (a_mirror[0] - b_ph) <= self._threshold and (a_mirror[1] - b_dh) <= self._threshold:
                    return True

        if b_mirror:
            for a_ph, a_dh in a_pairs:
                if (b_mirror[0] - a_ph) <= self._threshold and (b_mirror[1] - a_dh) <= self._threshold:
                    return True

        return False

    def _get_hash_pairs(
        self, img: ImageRecord,
    ) -> list[tuple[imagehash.ImageHash, imagehash.ImageHash]]:
        """Get paired (phash, dhash) for each rotation of an image."""
        rotations = [
            (img.phash_0, img.dhash_0),
            (img.phash_90, img.dhash_90),
            (img.phash_180, img.dhash_180),
            (img.phash_270, img.dhash_270),
        ]
        pairs = []
        for ph_str, dh_str in rotations:
            if ph_str and dh_str:
                try:
                    pairs.append((
                        imagehash.hex_to_hash(ph_str),
                        imagehash.hex_to_hash(dh_str),
                    ))
                except Exception:
                    pass
        return pairs

    def _get_mirror_pair(
        self, img: ImageRecord,
    ) -> tuple[imagehash.ImageHash, imagehash.ImageHash] | None:
        """Get the (phash, dhash) pair for the horizontal mirror of an image."""
        ph_str = img.phash_hmirror
        dh_str = img.dhash_hmirror
        if ph_str and dh_str:
            try:
                return (
                    imagehash.hex_to_hash(ph_str),
                    imagehash.hex_to_hash(dh_str),
                )
            except Exception:
                pass
        return None

    def _get_file_size(
        self, image_id: int, images: list[ImageRecord]
    ) -> int | None:
        """Get file size for an image from the list."""
        for img in images:
            if img.id == image_id:
                return img.file_size
        return None
