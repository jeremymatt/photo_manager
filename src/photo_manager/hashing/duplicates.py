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

    def __init__(self, db: DatabaseManager, threshold: int = 5):
        self._db = db
        self._threshold = threshold

    def find_duplicates(
        self,
        progress_callback: ProgressCallback | None = None,
    ) -> list[list[int]]:
        """Find groups of duplicate images in the database.

        Two images are considered duplicates when BOTH their pHash AND dHash
        are within the threshold distance, checking all rotation combinations
        (0-0, 0-90, 90-0, 90-90).

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
        """Check if two images are duplicates using rotation-aware hash comparison."""
        # Get all pHash values for each image
        a_phashes = self._get_hash_values(a.phash_0, a.phash_90)
        b_phashes = self._get_hash_values(b.phash_0, b.phash_90)
        a_dhashes = self._get_hash_values(a.dhash_0, a.dhash_90)
        b_dhashes = self._get_hash_values(b.dhash_0, b.dhash_90)

        if not a_phashes or not b_phashes or not a_dhashes or not b_dhashes:
            return False

        # Check all rotation combinations
        # Both pHash AND dHash must match for at least one rotation combo
        for a_ph in a_phashes:
            for b_ph in b_phashes:
                phash_dist = a_ph - b_ph
                if phash_dist <= self._threshold:
                    # pHash matches - now check dHash at same rotations
                    for a_dh in a_dhashes:
                        for b_dh in b_dhashes:
                            dhash_dist = a_dh - b_dh
                            if dhash_dist <= self._threshold:
                                return True
        return False

    def _get_hash_values(
        self, hash_0: str | None, hash_90: str | None
    ) -> list[imagehash.ImageHash]:
        """Convert hash strings to ImageHash objects."""
        result = []
        if hash_0:
            try:
                result.append(imagehash.hex_to_hash(hash_0))
            except Exception:
                pass
        if hash_90:
            try:
                result.append(imagehash.hex_to_hash(hash_90))
            except Exception:
                pass
        return result

    def _get_file_size(
        self, image_id: int, images: list[ImageRecord]
    ) -> int | None:
        """Get file size for an image from the list."""
        for img in images:
            if img.id == image_id:
                return img.file_size
        return None
