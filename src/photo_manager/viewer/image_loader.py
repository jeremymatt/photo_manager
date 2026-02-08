"""Background image loading, caching, and navigation."""

from __future__ import annotations

import os
import random
from collections import OrderedDict
from pathlib import Path
from typing import Any

from PIL import Image, ImageQt
from PyQt6.QtCore import QThread, pyqtSignal, QObject, QMutex, QMutexLocker
from PyQt6.QtGui import QPixmap, QImage

from photo_manager.scanner.exif import get_oriented_image


def pil_to_qpixmap(pil_image: Image.Image) -> QPixmap:
    """Convert a PIL Image to a QPixmap."""
    if pil_image.mode == "RGBA":
        qimage = QImage(
            pil_image.tobytes("raw", "RGBA"),
            pil_image.width, pil_image.height,
            4 * pil_image.width,
            QImage.Format.Format_RGBA8888,
        )
    else:
        rgb = pil_image.convert("RGB")
        qimage = QImage(
            rgb.tobytes("raw", "RGB"),
            rgb.width, rgb.height,
            3 * rgb.width,
            QImage.Format.Format_RGB888,
        )
    return QPixmap.fromImage(qimage)


class ImageCache:
    """LRU cache for loaded QPixmap objects."""

    def __init__(self, max_size_mb: int = 512):
        self._cache: OrderedDict[int, QPixmap] = OrderedDict()
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._current_size = 0

    def get(self, index: int) -> QPixmap | None:
        if index in self._cache:
            self._cache.move_to_end(index)
            return self._cache[index]
        return None

    def put(self, index: int, pixmap: QPixmap) -> None:
        if index in self._cache:
            self._current_size -= self._estimate_size(self._cache[index])
            del self._cache[index]

        size = self._estimate_size(pixmap)
        while self._current_size + size > self._max_size_bytes and self._cache:
            _, evicted = self._cache.popitem(last=False)
            self._current_size -= self._estimate_size(evicted)

        self._cache[index] = pixmap
        self._current_size += size
        self._cache.move_to_end(index)

    def clear(self) -> None:
        self._cache.clear()
        self._current_size = 0

    def __contains__(self, index: int) -> bool:
        return index in self._cache

    def _estimate_size(self, pixmap: QPixmap) -> int:
        img = pixmap.toImage()
        return img.sizeInBytes() if not img.isNull() else 0


class PreloadWorker(QThread):
    """Background thread that loads images into QPixmaps."""

    image_loaded = pyqtSignal(int, QPixmap)  # index, pixmap

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._requests: list[tuple[int, str]] = []
        self._mutex = QMutex()
        self._running = True

    def add_request(self, index: int, filepath: str) -> None:
        with QMutexLocker(self._mutex):
            # Don't add duplicates
            if not any(r[0] == index for r in self._requests):
                self._requests.append((index, filepath))

    def run(self) -> None:
        while self._running:
            request = None
            with QMutexLocker(self._mutex):
                if self._requests:
                    request = self._requests.pop(0)

            if request is None:
                self.msleep(50)
                continue

            index, filepath = request
            try:
                pil_img = get_oriented_image(filepath)
                pixmap = pil_to_qpixmap(pil_img)
                pil_img.close()
                self.image_loaded.emit(index, pixmap)
            except Exception:
                pass

    def stop(self) -> None:
        self._running = False
        self.wait()


class ImageLoader(QObject):
    """Manages the file list, navigation, caching, and background preloading."""

    image_ready = pyqtSignal(int, QPixmap)  # index, pixmap
    image_list_changed = pyqtSignal()

    def __init__(
        self,
        file_list: list[str],
        preload_next: int = 3,
        retain_previous: int = 2,
        cache_size_mb: int = 512,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._original_files = list(file_list)
        self._files = list(file_list)
        self._current_index = 0
        self._random_order = False
        self._shuffled_indices: list[int] = []
        self._preload_next = preload_next
        self._retain_prev = retain_previous

        self._cache = ImageCache(max_size_mb=cache_size_mb)
        self._worker = PreloadWorker()
        self._worker.image_loaded.connect(self._on_image_loaded)
        self._worker.start()

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def total(self) -> int:
        return len(self._files)

    @property
    def current_filepath(self) -> str:
        if not self._files:
            return ""
        return self._files[self._effective_index(self._current_index)]

    @property
    def random_order(self) -> bool:
        return self._random_order

    def current_pixmap(self) -> QPixmap | None:
        return self._cache.get(self._effective_index(self._current_index))

    def goto(self, index: int) -> None:
        if not self._files:
            return
        self._current_index = max(0, min(index, len(self._files) - 1))
        self._load_current()

    def next(self) -> None:
        if not self._files:
            return
        self._current_index = (self._current_index + 1) % len(self._files)
        self._load_current()

    def previous(self) -> None:
        if not self._files:
            return
        self._current_index = (self._current_index - 1) % len(self._files)
        self._load_current()

    def next_folder(self) -> None:
        if not self._files:
            return
        current_dir = str(Path(self.current_filepath).parent)
        start = self._current_index
        idx = (start + 1) % len(self._files)
        while idx != start:
            eff = self._effective_index(idx)
            if str(Path(self._files[eff]).parent) != current_dir:
                self._current_index = idx
                self._load_current()
                return
            idx = (idx + 1) % len(self._files)

    def prev_folder(self) -> None:
        if not self._files:
            return
        current_dir = str(Path(self.current_filepath).parent)
        start = self._current_index
        idx = (start - 1) % len(self._files)
        # First, find a file in a different (previous) folder
        while idx != start:
            eff = self._effective_index(idx)
            if str(Path(self._files[eff]).parent) != current_dir:
                break
            idx = (idx - 1) % len(self._files)
        if idx == start:
            return
        # Now rewind to the first file in that folder
        target_dir = str(Path(self._files[self._effective_index(idx)]).parent)
        while True:
            prev = (idx - 1) % len(self._files)
            eff = self._effective_index(prev)
            if str(Path(self._files[eff]).parent) != target_dir:
                break
            idx = prev
            if idx == start:
                break
        self._current_index = idx
        self._load_current()

    def toggle_random_order(self) -> None:
        self._random_order = not self._random_order
        if self._random_order:
            self._shuffled_indices = list(range(len(self._files)))
            random.shuffle(self._shuffled_indices)
            # Put current at position 0
            if self._files:
                cur_eff = self._current_index
                try:
                    pos = self._shuffled_indices.index(cur_eff)
                    self._shuffled_indices[0], self._shuffled_indices[pos] = (
                        self._shuffled_indices[pos], self._shuffled_indices[0]
                    )
                except ValueError:
                    pass
                self._current_index = 0
        else:
            # Restore sequential position
            if self._shuffled_indices and self._current_index < len(self._shuffled_indices):
                self._current_index = self._shuffled_indices[self._current_index]
            self._shuffled_indices.clear()
        self._cache.clear()
        self._load_current()

    def shutdown(self) -> None:
        self._worker.stop()

    def _effective_index(self, idx: int) -> int:
        if self._random_order and self._shuffled_indices:
            return self._shuffled_indices[idx % len(self._shuffled_indices)]
        return idx

    def _load_current(self) -> None:
        if not self._files:
            return
        eff = self._effective_index(self._current_index)
        cached = self._cache.get(eff)
        if cached is not None:
            self.image_ready.emit(self._current_index, cached)
        else:
            self._worker.add_request(eff, self._files[eff])

        # Preload surrounding images
        for offset in range(1, self._preload_next + 1):
            future_idx = (self._current_index + offset) % len(self._files)
            future_eff = self._effective_index(future_idx)
            if future_eff not in self._cache:
                self._worker.add_request(future_eff, self._files[future_eff])

    def _on_image_loaded(self, index: int, pixmap: QPixmap) -> None:
        self._cache.put(index, pixmap)
        # Check if this is for the current image
        eff = self._effective_index(self._current_index)
        if index == eff:
            self.image_ready.emit(self._current_index, pixmap)


def collect_image_files(directory: str | Path, recursive: bool = True) -> list[str]:
    """Collect all image files from a directory, sorted alphabetically."""
    directory = Path(directory)
    supported = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".ico"}
    ignore = {"Thumbs.db", ".DS_Store"}
    files: list[str] = []

    if recursive:
        for root, dirs, filenames in os.walk(directory):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in sorted(filenames):
                if fn.startswith(".") or fn in ignore:
                    continue
                if Path(fn).suffix.lower() in supported:
                    files.append(str(Path(root) / fn))
    else:
        for fn in sorted(os.listdir(directory)):
            fp = directory / fn
            if fp.is_file() and fn not in ignore and not fn.startswith("."):
                if fp.suffix.lower() in supported:
                    files.append(str(fp))
    return files
