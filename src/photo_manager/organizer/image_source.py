"""DB-backed image list with query filtering for the organizer."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from PyQt6.QtCore import QObject, pyqtSignal

from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import DuplicateGroup, DuplicateGroupMember, ImageRecord
from photo_manager.query.engine import QueryEngine


# Two areas within this ratio (largest / smallest) are treated as tied;
# file_size becomes the tiebreaker. Picked so a few percent of pixel
# trim doesn't push a high-quality re-encode below a low-bpp original.
_AREA_TIE_RATIO = 1.05

T = TypeVar("T")


def _quality_order(items: list[tuple[T, ImageRecord]]) -> list[tuple[T, ImageRecord]]:
    """Sort (payload, record) pairs by perceived quality, best first.

    Cluster-then-sort: by area desc, then group consecutive items whose
    area is within `_AREA_TIE_RATIO` of the cluster's leader (largest)
    area; within each cluster sort by file_size desc.

    This avoids the bucket-boundary bug of `round(log(area))`: two areas
    only a few percent apart could land in different buckets purely by
    where they fell relative to the rounding boundary.
    """
    def area(it: tuple[T, ImageRecord]) -> int:
        r = it[1]
        return (r.width or 0) * (r.height or 0)

    def file_size(it: tuple[T, ImageRecord]) -> int:
        return it[1].file_size or 0

    by_area = sorted(items, key=area, reverse=True)

    clusters: list[list[tuple[T, ImageRecord]]] = []
    current: list[tuple[T, ImageRecord]] = []
    leader_area: int = 0
    for it in by_area:
        a = area(it)
        if not current:
            current = [it]
            leader_area = a
            continue
        # Item joins current cluster iff its area is within tolerance of
        # the leader area. Anchoring to leader (not previous) prevents
        # transitive creep across many slightly-shrinking sizes.
        if a > 0 and a * _AREA_TIE_RATIO >= leader_area:
            current.append(it)
        else:
            clusters.append(current)
            current = [it]
            leader_area = a
    if current:
        clusters.append(current)

    out: list[tuple[T, ImageRecord]] = []
    for cluster in clusters:
        cluster.sort(key=file_size, reverse=True)
        out.extend(cluster)
    return out


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
        self._folder_filter: str | None = None
        self._folder_filtered_indices: list[int] = []
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
        if self._folder_filter is not None:
            return len(self._folder_filtered_indices)
        return len(self._records)

    @property
    def is_filtered(self) -> bool:
        return (
            self._delete_filter
            or self._dup_filter
            or self._folder_filter is not None
        )

    @property
    def folder_filter(self) -> str | None:
        return self._folder_filter

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
        if self._folder_filter is not None:
            if 0 <= index < len(self._folder_filtered_indices):
                return self._records[self._folder_filtered_indices[index]]
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
        if self._folder_filter is not None:
            return [
                self._resolve_path(self._records[i].filepath)
                for i in self._folder_filtered_indices
            ]
        return [
            self._resolve_path(r.filepath) for r in self._records
        ]

    def available_folders(self) -> list[str]:
        """Sorted list of distinct parent folders across the (unfiltered) records."""
        seen: set[str] = set()
        for r in self._records:
            seen.add(self._record_folder(r))
        return sorted(seen)

    def filepaths_in_folder(self, folder: str) -> list[str]:
        """Absolute filepaths of records whose parent folder matches `folder`."""
        target = str(Path(folder))
        return [
            self._resolve_path(r.filepath)
            for r in self._records
            if self._record_folder(r) == target
        ]

    def first_unmarked_dup_group_index(self) -> int:
        """Index of the first dup group where no member has `to_delete=True`.

        Returns 0 if every group already has at least one member marked
        for deletion (or there are no groups). Useful for skipping ahead
        on dup-review entry past groups the user has already processed.
        """
        if not self._dup_groups:
            return 0
        records_by_id = {r.id: r for r in self._records if r.id is not None}
        for i, group in enumerate(self._dup_groups):
            any_marked = any(
                records_by_id[m.image_id].to_delete
                for m in group.members
                if m.image_id in records_by_id
            )
            if not any_marked:
                return i
        return 0

    def filepaths_in_dup_group(self, group_index: int) -> list[str]:
        """Absolute filepaths of members of the dup group at the given index.

        Returned in the same quality order the dup view uses (see
        `_quality_order`) so prefetch matches display order.
        """
        if not (0 <= group_index < len(self._dup_groups)):
            return []
        member_ids = {m.image_id for m in self._dup_groups[group_index].members}
        items = [(r, r) for r in self._records if r.id in member_ids]
        ordered = _quality_order(items)
        return [self._resolve_path(r.filepath) for r, _ in ordered]

    def folder_for_index(self, index: int) -> str | None:
        """Parent folder of the record at the given (filtered-view) index."""
        record = self.get_record(index)
        if record is None:
            return None
        return self._record_folder(record)

    def set_folder_filter(self, folder: str | None) -> None:
        """Restrict visible records to those whose parent folder matches.

        Pass None to clear the folder filter.
        """
        self._folder_filter = folder
        self._rebuild_folder_filter()
        self.images_changed.emit()

    def _record_folder(self, record: ImageRecord) -> str:
        return str(Path(self._resolve_path(record.filepath)).parent)

    def _rebuild_folder_filter(self) -> None:
        if self._folder_filter is None:
            self._folder_filtered_indices = []
            return
        target = str(Path(self._folder_filter))
        self._folder_filtered_indices = [
            i for i, r in enumerate(self._records)
            if self._record_folder(r) == target
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
        if self._folder_filter is not None:
            self._rebuild_folder_filter()

    def _rebuild_dup_filter(self) -> None:
        """Rebuild filtered indices for the current duplicate group.

        Order is determined by `_quality_order` (cluster by area within
        ~5%, then sort by file_size within each cluster).
        """
        group = self.current_dup_group
        if group is None:
            self._dup_filtered_indices = []
            return

        member_ids = {m.image_id for m in group.members}
        members = [
            (i, r) for i, r in enumerate(self._records)
            if r.id in member_ids
        ]
        ordered = _quality_order(members)
        self._dup_filtered_indices = [idx for idx, _ in ordered]

    def _resolve_path(self, filepath: str) -> str:
        """Resolve a relative DB path to an absolute path."""
        p = Path(filepath)
        if p.is_absolute():
            return str(p)
        return str(self._db_dir / p)
