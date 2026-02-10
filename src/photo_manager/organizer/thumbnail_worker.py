"""Background thumbnail generation for the grid view."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QMutex, QWaitCondition
from PyQt6.QtGui import QPixmap

from photo_manager.scanner.exif import get_oriented_image
from photo_manager.viewer.image_loader import pil_to_qpixmap


class ThumbnailCache:
    """LRU cache for thumbnail QPixmaps."""

    def __init__(self, max_count: int = 500):
        self._max_count = max_count
        self._cache: OrderedDict[int, QPixmap] = OrderedDict()

    def get(self, index: int) -> QPixmap | None:
        if index in self._cache:
            self._cache.move_to_end(index)
            return self._cache[index]
        return None

    def put(self, index: int, pixmap: QPixmap) -> None:
        if index in self._cache:
            self._cache.move_to_end(index)
        else:
            self._cache[index] = pixmap
        while len(self._cache) > self._max_count:
            self._cache.popitem(last=False)

    def remove(self, index: int) -> None:
        self._cache.pop(index, None)

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


class _ThumbnailThread(QThread):
    """Worker thread that generates thumbnails from a queue."""

    thumbnail_ready = pyqtSignal(int, QPixmap)

    def __init__(self, thumb_size: tuple[int, int], parent=None):
        super().__init__(parent)
        self._thumb_size = thumb_size
        self._queue: list[tuple[int, str]] = []
        self._mutex = QMutex()
        self._condition = QWaitCondition()
        self._running = True

    def enqueue(self, index: int, filepath: str) -> None:
        self._mutex.lock()
        # Remove any existing request for this index
        self._queue = [
            (i, p) for i, p in self._queue if i != index
        ]
        self._queue.append((index, filepath))
        self._mutex.unlock()
        self._condition.wakeOne()

    def stop(self) -> None:
        self._mutex.lock()
        self._running = False
        self._mutex.unlock()
        self._condition.wakeOne()
        self.wait()

    def run(self) -> None:
        while True:
            self._mutex.lock()
            while self._running and not self._queue:
                self._condition.wait(self._mutex)
            if not self._running:
                self._mutex.unlock()
                break
            index, filepath = self._queue.pop(0)
            self._mutex.unlock()

            pixmap = self._generate_thumbnail(filepath)
            if pixmap is not None:
                self.thumbnail_ready.emit(index, pixmap)

    def _generate_thumbnail(self, filepath: str) -> QPixmap | None:
        try:
            img = get_oriented_image(filepath)
            img.thumbnail(self._thumb_size, Image.Resampling.LANCZOS)
            return pil_to_qpixmap(img)
        except Exception:
            return None


class ThumbnailWorker(QObject):
    """Manages thumbnail generation with caching."""

    thumbnail_ready = pyqtSignal(int, QPixmap)

    def __init__(
        self,
        thumb_size: tuple[int, int] = (256, 256),
        cache_count: int = 500,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._cache = ThumbnailCache(cache_count)
        self._thread = _ThumbnailThread(thumb_size)
        self._thread.thumbnail_ready.connect(self._on_thumbnail_ready)
        self._thread.start()

    def request(self, index: int, filepath: str) -> QPixmap | None:
        """Request a thumbnail. Returns cached pixmap or None if pending."""
        cached = self._cache.get(index)
        if cached is not None:
            return cached
        self._thread.enqueue(index, filepath)
        return None

    def invalidate(self, index: int, filepath: str) -> None:
        """Remove a cached thumbnail and re-request it from disk."""
        self._cache.remove(index)
        self._thread.enqueue(index, filepath)

    def clear_cache(self) -> None:
        self._cache.clear()

    def shutdown(self) -> None:
        self._thread.stop()

    def _on_thumbnail_ready(self, index: int, pixmap: QPixmap) -> None:
        self._cache.put(index, pixmap)
        self.thumbnail_ready.emit(index, pixmap)
