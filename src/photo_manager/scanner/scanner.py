"""Directory scanner for finding and importing images."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

from PIL import Image

from photo_manager.config.config import ConfigManager
from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import ImageRecord, ScanResult
from photo_manager.scanner.datetime_parser import parse_datetime
from photo_manager.scanner.exif import extract_exif
from photo_manager.scanner.tag_template import (
    TagTemplate,
    load_template_file,
    match_filepath,
    validate_template,
)

logger = logging.getLogger(__name__)

# Callback signature: (current_count, total_count, filepath)
ProgressCallback = Callable[[int, int, str], None]


class DirectoryScanner:
    """Recursively scan directories for images and add them to the database."""

    def __init__(
        self,
        db: DatabaseManager,
        config: ConfigManager | None = None,
    ):
        self._db = db
        self._config = config
        self._supported_formats = self._get_supported_formats()
        self._ignore_patterns = self._get_ignore_patterns()
        self._max_file_size = self._get_max_file_size()
        self._ignore_hidden = True
        if config:
            self._ignore_hidden = config.get(
                "file_scanning.ignore_hidden_files", True
            )

    def scan_directory(
        self,
        directory: str | Path,
        templates: list[TagTemplate] | None = None,
        progress_callback: ProgressCallback | None = None,
        recursive: bool = True,
    ) -> ScanResult:
        """Scan a directory for images and add them to the database.

        Args:
            directory: Path to the directory to scan.
            templates: Tag templates for extracting tags from paths.
                If None, looks for load_template.txt in the directory.
            progress_callback: Called with (current, total, filepath) for progress.
            recursive: Whether to scan subdirectories.

        Returns:
            ScanResult with counts of found/added/skipped/error files.
        """
        directory = Path(directory).resolve()
        if not directory.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")

        # Load templates from file if not provided
        if templates is None:
            template_path = directory / "load_template.txt"
            if template_path.exists():
                templates = load_template_file(str(template_path))
            else:
                templates = []

        # Collect all image files first
        image_files = self._find_image_files(directory, recursive)
        result = ScanResult(total_found=len(image_files))

        # Process each file
        db_dir = self._db.db_path.parent.resolve() if self._db.db_path else directory
        for i, filepath in enumerate(image_files):
            if progress_callback:
                progress_callback(i + 1, len(image_files), str(filepath))
            try:
                # Compute relative path from DB location
                try:
                    rel_path = filepath.relative_to(db_dir)
                except ValueError:
                    rel_path = filepath
                rel_path_str = str(rel_path).replace("\\", "/")

                # Skip if already in database
                existing = self._db.get_image_by_path(rel_path_str)
                if existing:
                    result.skipped += 1
                    continue

                # Extract metadata
                image_record = self._process_image(filepath, rel_path_str)
                if image_record is None:
                    result.errors += 1
                    result.error_files.append(str(filepath))
                    continue

                # Add to database
                image_id = self._db.add_image(image_record)

                # Apply tag templates
                if templates:
                    tag_values = match_filepath(rel_path_str, templates)
                    for tag_path, value in tag_values.items():
                        tag_def = self._db.resolve_tag_path(tag_path)
                        if tag_def:
                            self._db.set_image_tag(image_id, tag_def.id, value)

                result.added += 1

            except Exception as e:
                logger.error(f"Error processing {filepath}: {e}")
                result.errors += 1
                result.error_files.append(str(filepath))

        return result

    def _find_image_files(
        self, directory: Path, recursive: bool
    ) -> list[Path]:
        """Find all image files in a directory."""
        image_files: list[Path] = []

        if recursive:
            walker = os.walk(directory)
        else:
            walker = [(str(directory), [], os.listdir(directory))]

        for root_str, dirs, files in walker:
            root = Path(root_str)

            # Filter hidden directories
            if self._ignore_hidden:
                dirs[:] = [d for d in dirs if not d.startswith(".")]

            for filename in sorted(files):
                # Skip hidden files
                if self._ignore_hidden and filename.startswith("."):
                    continue

                # Skip ignore patterns
                if any(filename == p for p in self._ignore_patterns):
                    continue

                # Check extension
                ext = Path(filename).suffix.lower().lstrip(".")
                if ext not in self._supported_formats:
                    continue

                filepath = root / filename

                # Check file size
                if self._max_file_size > 0:
                    try:
                        size = filepath.stat().st_size
                        if size > self._max_file_size:
                            continue
                    except OSError:
                        continue

                image_files.append(filepath)

        return image_files

    def _process_image(
        self, filepath: Path, rel_path: str
    ) -> ImageRecord | None:
        """Extract metadata from an image file and create an ImageRecord."""
        try:
            exif_data = extract_exif(filepath)

            record = ImageRecord(
                filepath=rel_path,
                filename=filepath.name,
                file_size=filepath.stat().st_size,
                width=exif_data.width,
                height=exif_data.height,
            )

            # DateTime (priority: EXIF > filename > path)
            dt = parse_datetime(filepath, exif_data)
            if dt:
                record.set_datetime(dt)

            # GPS
            if exif_data.gps_latitude is not None and exif_data.gps_longitude is not None:
                record.latitude = f"{exif_data.gps_latitude:.6f}"
                record.longitude = f"{exif_data.gps_longitude:.6f}"
                record.has_lat_lon = True

            return record

        except Exception as e:
            logger.error(f"Failed to process image {filepath}: {e}")
            return None

    def _get_supported_formats(self) -> set[str]:
        if self._config:
            formats = self._config.get("file_scanning.supported_formats", [])
            if formats:
                return set(f.lower() for f in formats)
        return {"jpg", "jpeg", "png", "gif", "bmp", "tiff", "tif", "webp", "ico"}

    def _get_ignore_patterns(self) -> list[str]:
        if self._config:
            return self._config.get("file_scanning.ignore_patterns", [])
        return ["Thumbs.db", ".DS_Store"]

    def _get_max_file_size(self) -> int:
        """Get max file size in bytes."""
        if self._config:
            mb = self._config.get("file_scanning.max_file_size_mb", 500)
            return mb * 1024 * 1024
        return 500 * 1024 * 1024
