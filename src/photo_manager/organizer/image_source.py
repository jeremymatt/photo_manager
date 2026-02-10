"""DB-backed image list with query filtering for the organizer."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import DuplicateGroup, DuplicateGroupMember, ImageRecord
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
        self._delete_filter: bool = False
        self._filtered_indices: list[int] = []
        self._dup_filter: bool = False
        self._dup_group_index: int = 0
        self._dup_groups: list[DuplicateGroup] = []
        self._dup_filtered_indices: list[int] = []
        self._db_dir = (
            db.db_path.parent.resolve() if db.db_path else Path(".")
        )
        self.refresh()

    @property
    def total(self) -> int:
        if self._dup_filter:
            return len(self._dup_filtered_indices)
        if self._delete_filter:
            return len(self._filtered_indices)
        return len(self._records)

    @property
    def is_filtered(self) -> bool:
        return self._delete_filter or self._dup_filter

    @property
    def is_dup_filtered(self) -> bool:
        return self._dup_filter

    @property
    def dup_group_count(self) -> int:
        return len(self._dup_groups)

    @property
    def current_dup_group_index(self) -> int:
        return self._dup_group_index

    @property
    def current_dup_group(self) -> DuplicateGroup | None:
        if not self._dup_groups:
            return None
        if 0 <= self._dup_group_index < len(self._dup_groups):
            return self._dup_groups[self._dup_group_index]
        return None

    @property
    def query_expression(self) -> str | None:
        return self._query

    def get_record(self, index: int) -> ImageRecord | None:
        if self._dup_filter:
            if 0 <= index < len(self._dup_filtered_indices):
                return self._records[self._dup_filtered_indices[index]]
            return None
        if self._delete_filter:
            if 0 <= index < len(self._filtered_indices):
                return self._records[self._filtered_indices[index]]
            return None
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
        if self._dup_filter:
            return [
                self._resolve_path(self._records[i].filepath)
                for i in self._dup_filtered_indices
            ]
        if self._delete_filter:
            return [
                self._resolve_path(self._records[i].filepath)
                for i in self._filtered_indices
            ]
        return [
            self._resolve_path(r.filepath) for r in self._records
        ]

    def get_dup_member(self, image_id: int) -> DuplicateGroupMember | None:
        """Get the DuplicateGroupMember for an image in the current group."""
        group = self.current_dup_group
        if group is None:
            return None
        for member in group.members:
            if member.image_id == image_id:
                return member
        return None

    def set_dup_filter(self, enabled: bool) -> None:
        """Toggle filtering to show only images in a duplicate group."""
        self._dup_filter = enabled
        if enabled:
            self._dup_groups = self._db.get_duplicate_groups()
            self._dup_group_index = 0
            self._rebuild_dup_filter()
        else:
            self._dup_groups = []
            self._dup_group_index = 0
            self._dup_filtered_indices = []
        self.images_changed.emit()

    def set_dup_group(self, index: int) -> None:
        """Switch to viewing a specific duplicate group by index."""
        if not self._dup_groups:
            return
        self._dup_group_index = max(0, min(index, len(self._dup_groups) - 1))
        self._rebuild_dup_filter()
        self.images_changed.emit()

    def reload_dup_groups(self) -> None:
        """Reload duplicate groups from DB (after member updates)."""
        if not self._dup_filter:
            return
        old_index = self._dup_group_index
        self._dup_groups = self._db.get_duplicate_groups()
        if self._dup_groups:
            self._dup_group_index = min(old_index, len(self._dup_groups) - 1)
            self._rebuild_dup_filter()
        else:
            self._dup_filter = False
            self._dup_filtered_indices = []
        self.images_changed.emit()

    def set_delete_filter(self, enabled: bool) -> None:
        """Toggle filtering to show only images marked for deletion."""
        self._delete_filter = enabled
        self._rebuild_filter()
        self.images_changed.emit()

    def apply_query(self, expression: str) -> None:
        """Filter images using a query expression."""
        self._query = expression
        self._records = self._query_engine.query(expression)
        self._rebuild_filter()
        self.images_changed.emit()

    def clear_query(self) -> None:
        """Remove filter, show all images."""
        self._query = None
        self._records = self._db.get_all_images()
        self._rebuild_filter()
        self.images_changed.emit()

    def refresh(self) -> None:
        """Reload from database (e.g., after import)."""
        if self._query:
            self._records = self._query_engine.query(self._query)
        else:
            self._records = self._db.get_all_images()
        self._rebuild_filter()
        self.images_changed.emit()

    def _rebuild_filter(self) -> None:
        """Rebuild filtered indices based on to_delete flag."""
        if self._delete_filter:
            self._filtered_indices = [
                i for i, r in enumerate(self._records) if r.to_delete
            ]
        else:
            self._filtered_indices = []
        if self._dup_filter:
            self._rebuild_dup_filter()

    def _rebuild_dup_filter(self) -> None:
        """Rebuild filtered indices for the current duplicate group.

        Matches group member image_ids against _records indices.
        Sorts by file_size descending (largest first).
        """
        group = self.current_dup_group
        if group is None:
            self._dup_filtered_indices = []
            return

        member_ids = {m.image_id for m in group.members}
        # Build (index, file_size) pairs for members found in records
        matches = []
        for i, r in enumerate(self._records):
            if r.id in member_ids:
                matches.append((i, r.file_size or 0))
        # Sort by file_size descending
        matches.sort(key=lambda x: x[1], reverse=True)
        self._dup_filtered_indices = [idx for idx, _ in matches]

    def _resolve_path(self, filepath: str) -> str:
        """Resolve a relative DB path to an absolute path."""
        p = Path(filepath)
        if p.is_absolute():
            return str(p)
        return str(self._db_dir / p)
