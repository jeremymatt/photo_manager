"""Data models for Photo Manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ImageRecord:
    """Represents an image and its metadata in the database."""

    id: int | None = None
    filepath: str = ""
    filename: str = ""
    file_size: int | None = None
    width: int | None = None
    height: int | None = None
    datetime_str: str | None = None  # ISO 8601
    year: int | None = None
    month: int | None = None
    day: int | None = None
    hour: int | None = None
    minute: int | None = None
    second: int | None = None
    latitude: str | None = None
    longitude: str | None = None
    has_lat_lon: bool = False
    city: str | None = None
    town: str | None = None
    state: str | None = None
    phash_0: str | None = None
    phash_90: str | None = None
    dhash_0: str | None = None
    dhash_90: str | None = None
    favorite: bool = False
    to_delete: bool = False
    reviewed: bool = False
    auto_tag_errors: bool = False
    date_added: str | None = None
    date_modified: str | None = None

    def set_datetime(self, dt: datetime) -> None:
        """Set all datetime fields from a datetime object."""
        self.datetime_str = dt.isoformat()
        self.year = dt.year
        self.month = dt.month
        self.day = dt.day
        self.hour = dt.hour
        self.minute = dt.minute
        self.second = dt.second


@dataclass
class TagDefinition:
    """A node in the tag tree (category or leaf tag)."""

    id: int | None = None
    name: str = ""
    parent_id: int | None = None
    data_type: str = "string"  # string, bool, int, datetime
    is_category: bool = False


@dataclass
class ImageTag:
    """Association between an image and a tag with a value."""

    id: int | None = None
    image_id: int = 0
    tag_id: int = 0
    value: str | None = None


@dataclass
class DuplicateGroup:
    """A group of images identified as potential duplicates."""

    id: int | None = None
    created_date: str | None = None
    members: list[DuplicateGroupMember] = field(default_factory=list)


@dataclass
class DuplicateGroupMember:
    """A member of a duplicate group."""

    id: int | None = None
    group_id: int = 0
    image_id: int = 0
    is_kept: bool = False
    is_not_duplicate: bool = False


@dataclass
class ScanResult:
    """Result of a directory scan operation."""

    total_found: int = 0
    added: int = 0
    skipped: int = 0
    errors: int = 0
    error_files: list[str] = field(default_factory=list)
