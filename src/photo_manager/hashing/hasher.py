"""Perceptual image hashing with rotation awareness."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import imagehash
from PIL import Image

from photo_manager.scanner.exif import get_oriented_image

logger = logging.getLogger(__name__)

# Callback: (current_count, total_count, filepath)
ProgressCallback = Callable[[int, int, str], None]


@dataclass
class ImageHashes:
    """Perceptual hashes for an image at two orientations."""

    phash_0: str
    phash_90: str
    dhash_0: str
    dhash_90: str


def compute_hashes(filepath: str | Path) -> ImageHashes | None:
    """Compute perceptual hashes for an image at 0 and 90 degree rotations.

    The image is first corrected for EXIF orientation, then hashed at
    its corrected orientation (0) and rotated 90 degrees.
    """
    try:
        img = get_oriented_image(filepath)
        # Convert to RGB if necessary (some formats like P or RGBA)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # Hash at 0 degrees (EXIF-corrected orientation)
        phash_0 = str(imagehash.phash(img))
        dhash_0 = str(imagehash.dhash(img))

        # Hash at 90 degrees
        img_90 = img.transpose(Image.Transpose.ROTATE_90)
        phash_90 = str(imagehash.phash(img_90))
        dhash_90 = str(imagehash.dhash(img_90))

        img.close()
        img_90.close()

        return ImageHashes(
            phash_0=phash_0,
            phash_90=phash_90,
            dhash_0=dhash_0,
            dhash_90=dhash_90,
        )
    except Exception as e:
        logger.error(f"Failed to compute hashes for {filepath}: {e}")
        return None


class BackgroundHasher:
    """Compute hashes for multiple images in background threads."""

    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._futures: list[tuple[int, str, Future]] = []

    def submit(self, image_id: int, filepath: str | Path) -> None:
        """Submit an image for background hashing."""
        future = self._executor.submit(compute_hashes, filepath)
        self._futures.append((image_id, str(filepath), future))

    def get_results(self) -> list[tuple[int, ImageHashes | None]]:
        """Get all completed results. Blocks until all are done."""
        results = []
        for image_id, filepath, future in self._futures:
            try:
                hashes = future.result()
                results.append((image_id, hashes))
            except Exception as e:
                logger.error(f"Hash computation failed for {filepath}: {e}")
                results.append((image_id, None))
        self._futures.clear()
        return results

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the thread pool."""
        self._executor.shutdown(wait=wait)
