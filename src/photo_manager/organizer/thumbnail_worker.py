"""Background thumbnail generation for the grid view.

The worker runs a single dedicated thread fed by two priority-ordered
queues:

- **foreground**: requested by visible cells; each entry carries the
  cell index so completion can be signalled back to that cell.
- **background**: prefetched (e.g., next folder, next dup group); cached
  on completion but no signal is emitted.

The cache is keyed by **filepath** so it survives view changes — the
grid can switch folders/dup-groups without losing prefetched work.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from PIL import Image
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QMutex, QWaitCondition
from PyQt6.QtGui import QPixmap

from photo_manager.scanner.exif import get_oriented_image
from photo_manager.viewer.image_loader import pil_to_qpixmap


class ThumbnailCache:
    """LRU cache for thumbnail QPixmaps keyed by filepath."""

    def __init__(self, max_count: int = 500):
        self._max_count = max_count
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()

    def get(self, filepath: str) -> QPixmap | None:
        if filepath in self._cache:
            self._cache.move_to_end(filepath)
            return self._cache[filepath]
        return None

    def put(self, filepath: str, pixmap: QPixmap) -> None:
        if filepath in self._cache:
            self._cache.move_to_end(filepath)
        self._cache[filepath] = pixmap
        while len(self._cache) > self._max_count:
            self._cache.popitem(last=False)

    def remove(self, filepath: str) -> None:
        self._cache.pop(filepath, None)

    def __contains__(self, filepath: str) -> bool:
        return filepath in self._cache

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


@dataclass
class _Job:
    filepath: str
    index: int  # -1 for background (no signal)


class _ThumbnailThread(QThread):
    """Worker thread that generates thumbnails from prioritized queues."""

    thumbnail_ready = pyqtSignal(int, QPixmap)

    def __init__(
        self,
        thumb_size: tuple[int, int],
        cache: ThumbnailCache,
        parent=None,
    ):
        super().__init__(parent)
        self._thumb_size = thumb_size
        self._cache = cache
        self._foreground: list[_Job] = []
        self._background: list[_Job] = []
        self._mutex = QMutex()
        self._condition = QWaitCondition()
        self._running = True

    def enqueue_foreground(self, index: int, filepath: str) -> None:
        self._mutex.lock()
        # Drop any existing foreground job for this filepath; the new
        # index supersedes (cell index can shift between view rebuilds).
        self._foreground = [j for j in self._foreground if j.filepath != filepath]
        self._foreground.append(_Job(filepath, index))
        self._mutex.unlock()
        self._condition.wakeOne()

    def set_background(self, filepaths: list[str]) -> None:
        """Replace the entire background queue with the given list."""
        self._mutex.lock()
        # Filter out anything currently in the foreground queue or already cached
        fg_paths = {j.filepath for j in self._foreground}
        new_bg = [
            _Job(fp, -1) for fp in filepaths
            if fp not in fg_paths and fp not in self._cache
        ]
        self._background = new_bg
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
            while self._running and not self._foreground and not self._background:
                self._condition.wait(self._mutex)
            if not self._running:
                self._mutex.unlock()
                break
            # Foreground always wins
            if self._foreground:
                job = self._foreground.pop(0)
            else:
                job = self._background.pop(0)
            self._mutex.unlock()

            # Cache may have been populated by a sibling job (race)
            cached = self._cache.get(job.filepath)
            if cached is not None:
                if job.index >= 0:
                    self.thumbnail_ready.emit(job.index, cached)
                continue

            pixmap = self._generate_thumbnail(job.filepath)
            if pixmap is None:
                continue
            self._cache.put(job.filepath, pixmap)
            if job.index >= 0:
                self.thumbnail_ready.emit(job.index, pixmap)

    def _generate_thumbnail(self, filepath: str) -> QPixmap | None:
        try:
            img = get_oriented_image(filepath)
            img.thumbnail(self._thumb_size, Image.Resampling.LANCZOS)
            return pil_to_qpixmap(img)
        except Exception:
            return None


class ThumbnailWorker(QObject):
    """Public API for thumbnail generation.

    `request(index, filepath)` is for cells the user is currently looking at;
    `prefetch(filepaths)` is for what they're likely to look at next.
    """

    thumbnail_ready = pyqtSignal(int, QPixmap)

    def __init__(
        self,
        thumb_size: tuple[int, int] = (256, 256),
        cache_count: int = 500,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._cache = ThumbnailCache(cache_count)
        self._thread = _ThumbnailThread(thumb_size, self._cache)
        self._thread.thumbnail_ready.connect(self.thumbnail_ready.emit)
        self._thread.start()

    def request(self, index: int, filepath: str) -> QPixmap | None:
        """Foreground request. Returns cached pixmap or None if pending."""
        cached = self._cache.get(filepath)
        if cached is not None:
            return cached
        self._thread.enqueue_foreground(index, filepath)
        return None

    def prefetch(self, filepaths: list[str]) -> None:
        """Replace the background queue with these filepaths (in order)."""
        self._thread.set_background(filepaths)

    def invalidate(self, filepath: str) -> None:
        """Evict a cached pixmap so the next request regenerates it."""
        self._cache.remove(filepath)

    def clear_cache(self) -> None:
        self._cache.clear()

    def shutdown(self) -> None:
        self._thread.stop()
