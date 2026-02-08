"""Tag template parser for mapping directory structures to tags.

Template syntax:
    {category.subcategory}  - capture path segment as tag value
    *                       - match any single path segment (not captured)
    .*                      - match any file extension

Examples:
    ./{datetime.year}/{event.vacation}/*
    ./{datetime.year}/{event.vacation}/{person}.*
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from photo_manager.db.manager import DatabaseManager


@dataclass
class TemplateSegment:
    """A single segment in a parsed template."""

    tag_path: str | None  # e.g. "datetime.year" or None for wildcard
    is_filename: bool = False  # True if this is the filename segment


@dataclass
class TagTemplate:
    """A parsed tag template that can match filepaths to extract tags."""

    raw_template: str
    segments: list[TemplateSegment]

    def match(self, filepath: str) -> dict[str, str] | None:
        """Match a filepath against this template.

        Returns a dict of {tag_path: value} if the filepath matches,
        or None if it doesn't match.
        """
        # Normalize the filepath to use forward slashes
        filepath = filepath.replace("\\", "/")
        # Strip leading ./ if present
        if filepath.startswith("./"):
            filepath = filepath[2:]

        parts = PurePosixPath(filepath).parts

        # Non-filename segments match directories, last segment matches filename
        dir_segments = [s for s in self.segments if not s.is_filename]
        file_segment = next(
            (s for s in self.segments if s.is_filename), None
        )

        # Split filepath into dir parts and filename
        if len(parts) < 1:
            return None

        filepath_dirs = parts[:-1]
        filepath_filename = parts[-1]

        # Check directory segment count matches
        if len(filepath_dirs) != len(dir_segments):
            return None

        result: dict[str, str] = {}

        # Match directory segments
        for seg, dir_part in zip(dir_segments, filepath_dirs):
            if seg.tag_path is not None:
                result[seg.tag_path] = dir_part

        # Match filename segment
        if file_segment is not None and file_segment.tag_path is not None:
            # Strip extension for capture
            name_without_ext = PurePosixPath(filepath_filename).stem
            result[file_segment.tag_path] = name_without_ext

        return result


def parse_template(template_str: str) -> TagTemplate:
    """Parse a template string into a TagTemplate.

    Template format: ./{tag.path}/{tag.path}/*
    """
    template_str = template_str.strip()
    # Normalize to forward slashes
    template_str = template_str.replace("\\", "/")
    # Strip leading ./
    if template_str.startswith("./"):
        template_str = template_str[2:]

    parts = template_str.split("/")
    segments: list[TemplateSegment] = []

    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1

        if part in ("*", ".*"):
            # Wildcard - matches anything, captures nothing
            segments.append(TemplateSegment(
                tag_path=None,
                is_filename=is_last,
            ))
        elif "{" in part:
            # Tag capture: extract tag path from {tag.path}
            match = re.match(r"^\{([^}]+)\}(\.\*)?$", part)
            if match:
                tag_path = match.group(1)
                segments.append(TemplateSegment(
                    tag_path=tag_path,
                    is_filename=is_last,
                ))
            else:
                # Malformed segment - treat as wildcard
                segments.append(TemplateSegment(
                    tag_path=None,
                    is_filename=is_last,
                ))
        else:
            # Literal segment - wildcard (doesn't capture)
            segments.append(TemplateSegment(
                tag_path=None,
                is_filename=is_last,
            ))

    return TagTemplate(raw_template=template_str, segments=segments)


def load_template_file(template_path: str) -> list[TagTemplate]:
    """Load tag templates from a load_template.txt file.

    Each non-empty, non-comment line is parsed as a template.
    Returns a list of TagTemplate objects.
    """
    templates: list[TagTemplate] = []
    with open(template_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            templates.append(parse_template(line))
    return templates


def validate_template(
    template: TagTemplate, db: DatabaseManager
) -> list[str]:
    """Validate a template's tag references against the database.

    Returns a list of warning messages for unknown tag paths.
    """
    warnings: list[str] = []
    for segment in template.segments:
        if segment.tag_path is None:
            continue
        tag_def = db.resolve_tag_path(segment.tag_path)
        if tag_def is None:
            warnings.append(
                f"Unknown tag path '{segment.tag_path}' in template "
                f"'{template.raw_template}'"
            )
    return warnings


def match_filepath(
    filepath: str, templates: list[TagTemplate]
) -> dict[str, str]:
    """Try to match a filepath against a list of templates.

    Returns the tag assignments from the first matching template,
    or an empty dict if no template matches.
    """
    for template in templates:
        result = template.match(filepath)
        if result is not None:
            return result
    return {}
