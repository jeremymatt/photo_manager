"""Background hash computation thread for the organizer."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from photo_manager.db.manager import DatabaseManager
from photo_manager.hashing.hasher import compute_hashes


class HashThread(QThread):
    """Compute perceptual hashes for unhashed images in a background thread.

    Opens its own DB connection since SQLite connections can't cross threads.
    """

    progress = pyqtSignal(int, int, str)  # current, total, filepath
    finished_hashing = pyqtSignal(int)  # hashed_count

    def __init__(self, db_path: str, parent=None):
        super().__init__(parent)
        self._db_path = db_path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        thread_db = DatabaseManager()
        thread_db.open_database(self._db_path)
        # Allow waiting up to 5s for write lock if main thread is writing
        thread_db._conn.execute("PRAGMA busy_timeout=5000")

        try:
            images = thread_db.get_all_images()
            unhashed = [
                img for img in images
                if img.phash_0 is None or img.phash_180 is None
                or img.phash_hmirror is None
            ]
            total = len(unhashed)
            hashed = 0

            for i, img in enumerate(unhashed):
                if self._cancelled:
                    break

                filepath = img.filepath
                p = Path(filepath)
                if not p.is_absolute():
                    db_dir = Path(self._db_path).parent
                    p = db_dir / p

                self.progress.emit(i + 1, total, str(p))

                result = compute_hashes(str(p))
                if result is not None:
                    img.phash_0 = result.phash_0
                    img.phash_90 = result.phash_90
                    img.phash_180 = result.phash_180
                    img.phash_270 = result.phash_270
                    img.dhash_0 = result.dhash_0
                    img.dhash_90 = result.dhash_90
                    img.dhash_180 = result.dhash_180
                    img.dhash_270 = result.dhash_270
                    img.phash_hmirror = result.phash_hmirror
                    img.dhash_hmirror = result.dhash_hmirror
                    thread_db.update_image(img)
                    hashed += 1

            self.finished_hashing.emit(hashed)
        except Exception:
            self.finished_hashing.emit(0)
        finally:
            thread_db.close()
