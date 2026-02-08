"""Export engine for organizing images into directory structures based on tags."""

from __future__ import annotations

import csv
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import ImageRecord, ImageTag

logger = logging.getLogger(__name__)

# Callback: (current_count, total_count, filepath)
ProgressCallback = Callable[[int, int, str], None]


@dataclass
class ExportSegment:
    """A segment in an export template."""

    tag_path: str | None  # e.g. "datetime.year" or None for literal
    expand: bool = False  # True if > operator used (expand subtree)
    literal: str | None = None  # For literal path segments


@dataclass
class ExportResult:
    """Result of an export operation."""

    total: int = 0
    exported: int = 0
    errors: int = 0
    error_files: list[str] = field(default_factory=list)


def parse_export_template(template: str) -> list[ExportSegment]:
    """Parse an export template string.

    Syntax:
        {tag.datetime.year}  - use tag value as directory name
        {tag.event>}         - expand tag subtree into directories
        literal              - literal directory name

    Example: "{tag.datetime.year}/{tag.event>}" =>
        [ExportSegment(tag_path="datetime.year"),
         ExportSegment(tag_path="event", expand=True)]
    """
    segments: list[ExportSegment] = []
    # Strip ROOT_EXPORT_DIR/ prefix if present
    template = re.sub(r"^ROOT_EXPORT_DIR/", "", template)
    template = template.strip("/")

    for part in template.split("/"):
        part = part.strip()
        if not part:
            continue

        match = re.match(r"^\{tag\.([^}]+?)(>)?\}$", part)
        if match:
            tag_path = match.group(1)
            expand = match.group(2) == ">"
            segments.append(ExportSegment(tag_path=tag_path, expand=expand))
        else:
            segments.append(ExportSegment(tag_path=None, literal=part))

    return segments


class ExportEngine:
    """Export images to a directory structure based on tags."""

    def __init__(self, db: DatabaseManager):
        self._db = db

    def export(
        self,
        images: list[ImageRecord],
        export_dir: str | Path,
        template: str,
        mode: str = "copy",  # "copy" or "move"
        export_csv: bool = False,
        progress_callback: ProgressCallback | None = None,
        dry_run: bool = False,
    ) -> ExportResult:
        """Export images to a directory structure.

        Args:
            images: List of images to export.
            export_dir: Root export directory.
            template: Export template string.
            mode: "copy" (leave originals) or "move" (remove originals, update DB).
            export_csv: Write image_metadata.csv.
            progress_callback: Progress callback.
            dry_run: If True, don't actually copy/move files.

        Returns:
            ExportResult with counts.
        """
        export_dir = Path(export_dir)
        segments = parse_export_template(template)
        result = ExportResult(total=len(images))
        csv_rows: list[dict] = []
        db_base = self._db.db_path.parent.resolve() if self._db.db_path else Path(".")

        for i, image in enumerate(images):
            if progress_callback:
                progress_callback(i + 1, len(images), image.filepath)

            try:
                # Build destination path from template
                dest_subpath = self._build_path(image, segments)
                if dest_subpath is None:
                    dest_subpath = "Other"

                dest_dir = export_dir / dest_subpath
                source_path = db_base / image.filepath

                if not source_path.exists():
                    logger.warning(f"Source file not found: {source_path}")
                    result.errors += 1
                    result.error_files.append(image.filepath)
                    continue

                dest_path = dest_dir / image.filename

                # Handle filename collisions
                if dest_path.exists():
                    stem = dest_path.stem
                    suffix = dest_path.suffix
                    counter = 1
                    while dest_path.exists():
                        dest_path = dest_dir / f"{stem}_{counter}{suffix}"
                        counter += 1

                if not dry_run:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    if mode == "move":
                        shutil.move(str(source_path), str(dest_path))
                        # Update database path
                        try:
                            new_rel = dest_path.relative_to(db_base)
                        except ValueError:
                            new_rel = dest_path
                        image.filepath = str(new_rel).replace("\\", "/")
                        image.filename = dest_path.name
                        self._db.update_image(image)
                        # Clean up empty source directories
                        self._cleanup_empty_dirs(source_path.parent, db_base)
                    else:
                        shutil.copy2(str(source_path), str(dest_path))

                if export_csv:
                    csv_rows.append(self._image_to_csv_row(image, dest_subpath))

                result.exported += 1

            except Exception as e:
                logger.error(f"Error exporting {image.filepath}: {e}")
                result.errors += 1
                result.error_files.append(image.filepath)

        # Write CSV
        if export_csv and csv_rows and not dry_run:
            self._write_csv(export_dir / "image_metadata.csv", csv_rows)

        return result

    def _build_path(
        self, image: ImageRecord, segments: list[ExportSegment]
    ) -> str | None:
        """Build a destination path for an image based on the export template."""
        parts: list[str] = []

        for segment in segments:
            if segment.literal is not None:
                parts.append(segment.literal)
                continue

            if segment.tag_path is None:
                continue

            value = self._get_tag_value(image, segment.tag_path, segment.expand)
            if value is None:
                parts.append("Unknown")
            else:
                parts.append(value)

        return "/".join(parts) if parts else None

    def _get_tag_value(
        self, image: ImageRecord, tag_path: str, expand: bool
    ) -> str | None:
        """Get the tag value for an image given a tag path.

        For fixed fields, reads directly from the image record.
        For dynamic tags, looks up in image_tags.
        If expand is True, builds a full subtree path.
        """
        # Check fixed fields first
        fixed_value = self._get_fixed_value(image, tag_path)
        if fixed_value is not None:
            return str(fixed_value)

        if image.id is None:
            return None

        # Dynamic tag lookup
        tag_def = self._db.resolve_tag_path(tag_path)
        if tag_def is None:
            return None

        if expand:
            # Get all child tags for this image under this category
            return self._get_expanded_tag_value(image.id, tag_def.id)
        else:
            # Get direct tag value
            tags = self._db.get_image_tags(image.id)
            for tag in tags:
                if tag.tag_id == tag_def.id and tag.value:
                    return tag.value
            # Check children for value
            children = self._db.get_tag_children(tag_def.id)
            for child in children:
                for tag in tags:
                    if tag.tag_id == child.id and tag.value:
                        return tag.value
            return None

    def _get_expanded_tag_value(
        self, image_id: int, tag_def_id: int
    ) -> str | None:
        """Build expanded directory path from tag subtree.

        For example, if an image has event>birthday>Alice,
        returns "birthday/Alice".
        """
        tags = self._db.get_image_tags(image_id)
        tag_ids = {t.tag_id for t in tags}

        # Find which children of this tag are assigned to the image
        def find_path(parent_id: int) -> list[str]:
            children = self._db.get_tag_children(parent_id)
            for child in children:
                if child.id in tag_ids:
                    # This child is tagged - check for deeper nesting
                    deeper = find_path(child.id)
                    if deeper:
                        return [child.name] + deeper
                    # Check if there's a value
                    for tag in tags:
                        if tag.tag_id == child.id and tag.value:
                            return [tag.value]
                    return [child.name]
            # Check for direct value on parent
            for tag in tags:
                if tag.tag_id == parent_id and tag.value:
                    return [tag.value]
            return []

        path_parts = find_path(tag_def_id)
        if not path_parts:
            return None

        # Combine multiple tag values with underscore
        return "/".join(path_parts)

    def _get_fixed_value(
        self, image: ImageRecord, tag_path: str
    ) -> str | int | None:
        """Get a value from fixed image record fields."""
        mapping = {
            "datetime.year": image.year,
            "datetime.month": image.month,
            "datetime.day": image.day,
            "datetime.hr": image.hour,
            "datetime.min": image.minute,
            "datetime.sec": image.second,
            "location.city": image.city,
            "location.town": image.town,
            "location.state": image.state,
        }
        return mapping.get(tag_path)

    def _image_to_csv_row(
        self, image: ImageRecord, dest_subpath: str
    ) -> dict:
        """Convert an image record to a CSV row dict."""
        row = {
            "filepath": image.filepath,
            "filename": image.filename,
            "export_path": dest_subpath,
            "width": image.width,
            "height": image.height,
            "datetime": image.datetime_str,
            "year": image.year,
            "latitude": image.latitude,
            "longitude": image.longitude,
            "favorite": image.favorite,
            "reviewed": image.reviewed,
        }
        # Add tag values
        if image.id is not None:
            tags = self._db.get_image_tags(image.id)
            for tag in tags:
                tag_def = self._db.get_tag_definition(tag.tag_id)
                if tag_def:
                    row[f"tag_{tag_def.name}"] = tag.value
        return row

    def _write_csv(self, path: Path, rows: list[dict]) -> None:
        """Write image metadata to CSV."""
        if not rows:
            return
        # Collect all possible fields
        all_fields: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    all_fields.append(key)
                    seen.add(key)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_fields)
            writer.writeheader()
            writer.writerows(rows)

    def _cleanup_empty_dirs(self, directory: Path, stop_at: Path) -> None:
        """Recursively remove empty directories up to stop_at."""
        try:
            while directory != stop_at and directory.is_dir():
                if any(directory.iterdir()):
                    break
                directory.rmdir()
                directory = directory.parent
        except OSError:
            pass
