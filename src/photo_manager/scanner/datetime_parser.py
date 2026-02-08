"""DateTime extraction with priority: EXIF > filename > folder path."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from photo_manager.scanner.exif import ExifData


def parse_datetime(
    filepath: str | Path, exif_data: ExifData | None = None
) -> datetime | None:
    """Extract datetime using priority: EXIF > filename > folder path.

    Returns the best datetime found, or None if no datetime could be determined.
    """
    # Priority 1: EXIF datetime
    if exif_data:
        exif_dt = (
            exif_data.datetime_original
            or exif_data.datetime_digitized
            or exif_data.datetime_modified
        )
        if exif_dt:
            return exif_dt

    filepath = Path(filepath)

    # Priority 2: Filename
    dt = _parse_from_filename(filepath.name)
    if dt:
        return dt

    # Priority 3: Folder path
    dt = _parse_from_path(filepath)
    if dt:
        return dt

    return None


# Patterns ordered from most specific to least specific
_FILENAME_PATTERNS: list[tuple[str, str]] = [
    # 2019-07-04_15-30-24 or 2019-07-04_15:30:24
    (r"(\d{4})-(\d{2})-(\d{2})[_\s](\d{2})[-:](\d{2})[-:](\d{2})",
     "%Y-%m-%d_%H-%M-%S"),
    # 20190704_153024 (common camera format)
    (r"(\d{4})(\d{2})(\d{2})[_\s-](\d{2})(\d{2})(\d{2})",
     "%Y%m%d_%H%M%S"),
    # IMG_20190704_153024
    (r"IMG[_-](\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})",
     "%Y%m%d_%H%M%S"),
    # 2019-07-04
    (r"(\d{4})-(\d{2})-(\d{2})", "%Y-%m-%d"),
    # 20190704
    (r"(\d{4})(\d{2})(\d{2})", "%Y%m%d"),
]


def _parse_from_filename(filename: str) -> datetime | None:
    """Try to extract a datetime from the filename."""
    stem = Path(filename).stem

    for pattern, fmt in _FILENAME_PATTERNS:
        match = re.search(pattern, stem)
        if match:
            groups = match.groups()
            try:
                if len(groups) == 6:
                    return datetime(
                        int(groups[0]), int(groups[1]), int(groups[2]),
                        int(groups[3]), int(groups[4]), int(groups[5]),
                    )
                elif len(groups) == 3:
                    return datetime(
                        int(groups[0]), int(groups[1]), int(groups[2]),
                    )
            except ValueError:
                continue
    return None


def _parse_from_path(filepath: Path) -> datetime | None:
    """Try to extract datetime info from the directory path.

    Looks for 4-digit years (1900-2099) in path components.
    """
    parts = filepath.parts
    for part in reversed(parts):
        match = re.match(r"^((?:19|20)\d{2})$", part)
        if match:
            try:
                year = int(match.group(1))
                return datetime(year, 1, 1)
            except ValueError:
                continue
    return None
