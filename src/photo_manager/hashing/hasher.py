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
    """Perceptual hashes for an image at four orientations plus mirror."""

    phash_0: str
    phash_90: str
    phash_180: str
    phash_270: str
    dhash_0: str
    dhash_90: str
    dhash_180: str
    dhash_270: str
    phash_hmirror: str = ""
    dhash_hmirror: str = ""


def compute_hashes(filepath: str | Path) -> ImageHashes | None:
    """Compute perceptual hashes for an image at 0, 90, 180, and 270 degrees.

    The image is first corrected for EXIF orientation, then hashed at
    all four rotations to enable rotation-aware duplicate detection.
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

        # Hash at 180 degrees
        img_180 = img.transpose(Image.Transpose.ROTATE_180)
        phash_180 = str(imagehash.phash(img_180))
        dhash_180 = str(imagehash.dhash(img_180))

        # Hash at 270 degrees
        img_270 = img.transpose(Image.Transpose.ROTATE_270)
        phash_270 = str(imagehash.phash(img_270))
        dhash_270 = str(imagehash.dhash(img_270))

        # Hash horizontal mirror (left-right flip at 0°)
        img_mirror = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        phash_hmirror = str(imagehash.phash(img_mirror))
        dhash_hmirror = str(imagehash.dhash(img_mirror))

        img.close()
        img_90.close()
        img_180.close()
        img_270.close()
        img_mirror.close()

        return ImageHashes(
            phash_0=phash_0,
            phash_90=phash_90,
            phash_180=phash_180,
            phash_270=phash_270,
            dhash_0=dhash_0,
            dhash_90=dhash_90,
            dhash_180=dhash_180,
            dhash_270=dhash_270,
            phash_hmirror=phash_hmirror,
            dhash_hmirror=dhash_hmirror,
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
