"""DB-backed image list with query filtering for the organizer."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import ImageRecord
from photo_manager.query.engine import QueryEngine


class ImageSource(QObject):
    """Provides a filtered, indexed list of images from a database."""

    images_changed = pyqtSignal()

    def __init__(
        self,
        db: DatabaseManager,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._db = db
        self._query_engine = QueryEngine(db)
        self._records: list[ImageRecord] = []
        self._query: str | None = None
        self._db_dir = (
            db.db_path.parent.resolve() if db.db_path else Path(".")
        )
        self.refresh()

    @property
    def total(self) -> int:
        return len(self._records)

    @property
    def query_expression(self) -> str | None:
        return self._query

    def get_record(self, index: int) -> ImageRecord | None:
        if 0 <= index < len(self._records):
            return self._records[index]
        return None

    def get_filepath(self, index: int) -> str:
        """Get absolute filepath for an image by index."""
        record = self.get_record(index)
        if record is None:
            return ""
        return self._resolve_path(record.filepath)

    def get_file_list(self) -> list[str]:
        """Get all absolute filepaths for feeding to ImageLoader."""
        return [
            self._resolve_path(r.filepath) for r in self._records
        ]

    def apply_query(self, expression: str) -> None:
        """Filter images using a query expression."""
        self._query = expression
        self._records = self._query_engine.query(expression)
        self.images_changed.emit()

    def clear_query(self) -> None:
        """Remove filter, show all images."""
        self._query = None
        self._records = self._db.get_all_images()
        self.images_changed.emit()

    def refresh(self) -> None:
        """Reload from database (e.g., after import)."""
        if self._query:
            self._records = self._query_engine.query(self._query)
        else:
            self._records = self._db.get_all_images()
        self.images_changed.emit()

    def _resolve_path(self, filepath: str) -> str:
        """Resolve a relative DB path to an absolute path."""
        p = Path(filepath)
        if p.is_absolute():
            return str(p)
        return str(self._db_dir / p)
