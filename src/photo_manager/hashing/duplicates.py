"""Duplicate detection using perceptual hashes.

Uses a BK-tree indexed on pHash to enumerate candidate pairs in
sub-quadratic time, then verifies each candidate by checking that BOTH
pHash and dHash are within the threshold at the same orientation pair.
Each image contributes up to 5 orientation variants (r0/90/180/270 +
horizontal mirror); a duplicate match requires any one variant pair
across two images to satisfy both-hash threshold.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

import pybktree

from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import ImageRecord

logger = logging.getLogger(__name__)

# Callback: (current_count, total_count). With BK-tree the meaning is
# "variants queried" / "total variants" — see DuplicateDetectionDialog.
ProgressCallback = Callable[[int, int], None]

THRESHOLD_MAX = 20


@dataclass(frozen=True)
class _Variant:
    image_id: int
    phash: int
    dhash: int


def _hex_to_int(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(s, 16)
    except ValueError:
        return None


def _bk_distance(a, b) -> int:
    return (a[0] ^ b[0]).bit_count()


class DuplicateDetector:
    """Detect duplicate images using perceptual hash comparison."""

    def __init__(self, db: DatabaseManager, threshold: int = 10):
        self._db = db
        self._threshold = max(0, min(int(threshold), THRESHOLD_MAX))

    def find_duplicates(
        self,
        progress_callback: ProgressCallback | None = None,
    ) -> list[list[int]]:
        """Find groups of duplicate images in the database.

        Two images are duplicates when ANY of their orientation variants
        (r0/90/180/270/hmirror) has BOTH pHash AND dHash within the
        threshold Hamming distance.

        Returns a list of groups, each a list of image IDs sorted by
        file_size descending.
        """
        images = self._db.get_all_images()
        # Map image_id -> file_size for sort, and only retain images that
        # have at least one usable (phash, dhash) variant.
        sizes: dict[int, int] = {}
        variants: list[_Variant] = []

        for img in images:
            if img.id is None:
                continue
            had_variant = False
            for ph_str, dh_str in (
                (img.phash_0, img.dhash_0),
                (img.phash_90, img.dhash_90),
                (img.phash_180, img.dhash_180),
                (img.phash_270, img.dhash_270),
                (img.phash_hmirror, img.dhash_hmirror),
            ):
                ph = _hex_to_int(ph_str)
                dh = _hex_to_int(dh_str)
                if ph is None or dh is None:
                    continue
                variants.append(_Variant(img.id, ph, dh))
                had_variant = True
            if had_variant:
                sizes[img.id] = img.file_size or 0

        total_variants = len(variants)
        if total_variants == 0:
            return []

        # Build BK-tree over (phash_int, variant_idx) tuples.
        items = [(v.phash, idx) for idx, v in enumerate(variants)]
        tree = pybktree.BKTree(_bk_distance, items)

        # Union-Find over image IDs
        parent: dict[int, int] = {img_id: img_id for img_id in sizes}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        seen_pairs: set[tuple[int, int]] = set()

        for idx, v in enumerate(variants):
            if progress_callback and (idx % 100 == 0 or idx == total_variants - 1):
                progress_callback(idx + 1, total_variants)

            for _dist, (_other_ph, other_idx) in tree.find(
                (v.phash, idx), self._threshold
            ):
                if other_idx == idx:
                    continue  # self
                ov = variants[other_idx]
                if ov.image_id == v.image_id:
                    continue  # same image, different orientation

                # Order pair so we only verify and union once per image-pair
                a_id, b_id = (
                    (v.image_id, ov.image_id)
                    if v.image_id < ov.image_id
                    else (ov.image_id, v.image_id)
                )
                if (a_id, b_id) in seen_pairs:
                    continue

                # phash already passed; verify dhash
                if (v.dhash ^ ov.dhash).bit_count() > self._threshold:
                    continue

                seen_pairs.add((a_id, b_id))
                union(a_id, b_id)

        if progress_callback:
            progress_callback(total_variants, total_variants)

        # Build groups
        groups: dict[int, list[int]] = {}
        for img_id in sizes:
            root = find(img_id)
            groups.setdefault(root, []).append(img_id)

        result: list[list[int]] = []
        for group_ids in groups.values():
            if len(group_ids) < 2:
                continue
            group_ids.sort(key=lambda i: sizes.get(i, 0), reverse=True)
            result.append(group_ids)

        return result

    def store_duplicate_groups(self, groups: list[list[int]]) -> list[int]:
        """Store duplicate groups in the database. Returns created group IDs."""
        return [self._db.create_duplicate_group(ids) for ids in groups]
