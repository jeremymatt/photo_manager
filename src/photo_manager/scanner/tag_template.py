"""Tag template parser for mapping directory structures to tags.

Template syntax (txt format):
    {category.subcategory}  - capture path segment as tag value
    *                       - match any single path segment (not captured)
    .*                      - match any file extension

Examples:
    ./{datetime.year}/{event.vacation}/*
    ./{datetime.year}/{event.vacation}/{person}.*

YAML format (load_template.yaml):
    version: 1
    pattern: "{scene}/{filename}.{ext}"
    options:
      case_insensitive: true
      require_full_match: true
      on_mismatch: tag_auto_tag_errors
    tags:
      scene: "{scene}"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from photo_manager.db.manager import DatabaseManager


@dataclass
class TemplateSegment:
    """A single segment in a parsed template."""

    tag_path: str | None  # e.g. "datetime.year" or None for wildcard
    is_filename: bool = False  # True if this is the filename segment


@dataclass
class TemplateOptions:
    """Options for YAML-based templates."""

    case_insensitive: bool = False
    require_full_match: bool = True
    on_mismatch: str = "skip_file"  # tag_auto_tag_errors, skip_file, fail_import


@dataclass
class TagTemplate:
    """A parsed tag template that can match filepaths to extract tags."""

    raw_template: str
    segments: list[TemplateSegment]
    options: TemplateOptions = field(default_factory=TemplateOptions)
    # Back-reference mapping: {tag_path: "{capture_name}"}
    tag_mapping: dict[str, str] = field(default_factory=dict)

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

        # First pass: capture all named groups from pattern segments
        captures: dict[str, str] = {}

        # Match directory segments
        for seg, dir_part in zip(dir_segments, filepath_dirs):
            if seg.tag_path is not None:
                captures[seg.tag_path] = dir_part

        # Match filename segment
        if file_segment is not None and file_segment.tag_path is not None:
            name_without_ext = PurePosixPath(filepath_filename).stem
            captures[file_segment.tag_path] = name_without_ext

        # If we have a tag_mapping (YAML format), resolve back-references
        if self.tag_mapping:
            result: dict[str, str] = {}
            for tag_path, ref in self.tag_mapping.items():
                resolved = _resolve_back_reference(ref, captures)
                if resolved is not None:
                    result[tag_path] = resolved
            return result

        # Legacy (txt format): captures are used directly as tag assignments
        return captures


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

    For YAML templates, validates the tag_mapping keys (DB tag paths).
    For txt templates, validates the segment tag_paths.
    Returns a list of warning messages for unknown tag paths.
    """
    warnings: list[str] = []

    if template.tag_mapping:
        # YAML format: validate tag_mapping keys (the actual DB paths)
        for tag_path in template.tag_mapping:
            tag_def = db.resolve_tag_path(tag_path)
            if tag_def is None:
                warnings.append(
                    f"Unknown tag path '{tag_path}' in template "
                    f"'{template.raw_template}'"
                )
    else:
        # txt format: validate segment tag paths
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


def _resolve_back_reference(
    ref: str, captures: dict[str, str]
) -> str | None:
    """Resolve a back-reference like '{scene}' against captured values."""
    match = re.match(r"^\{([^}]+)\}$", ref)
    if match:
        capture_name = match.group(1)
        return captures.get(capture_name)
    # Literal value (no braces)
    return ref


def _parse_yaml_pattern(pattern: str) -> list[TemplateSegment]:
    """Parse a YAML template pattern into segments.

    Pattern format: "{scene}/{filename}.{ext}"
    Named groups like {name} capture path segments.
    {filename} and {ext} are special: they match the filename and extension.
    """
    pattern = pattern.strip().replace("\\", "/")
    if pattern.startswith("./"):
        pattern = pattern[2:]

    parts = pattern.split("/")
    segments: list[TemplateSegment] = []

    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1

        if part in ("*", ".*"):
            segments.append(TemplateSegment(tag_path=None, is_filename=is_last))
        elif "{" in part:
            # Check for filename pattern like {filename}.{ext}
            fname_match = re.match(
                r"^\{([^}]+)\}\.\{([^}]+)\}$", part
            )
            if fname_match and is_last:
                # Filename + extension pattern — capture just the name part
                capture_name = fname_match.group(1)
                segments.append(TemplateSegment(
                    tag_path=capture_name, is_filename=True
                ))
            else:
                # Simple capture group like {scene}
                cap_match = re.match(r"^\{([^}]+)\}(\.\*)?$", part)
                if cap_match:
                    segments.append(TemplateSegment(
                        tag_path=cap_match.group(1), is_filename=is_last
                    ))
                else:
                    segments.append(TemplateSegment(
                        tag_path=None, is_filename=is_last
                    ))
        else:
            segments.append(TemplateSegment(tag_path=None, is_filename=is_last))

    return segments


def load_yaml_template(template_path: str) -> TagTemplate:
    """Load a YAML-format tag template.

    Expected format:
        version: 1
        pattern: "{scene}/{filename}.{ext}"
        options:
          case_insensitive: true
          require_full_match: true
          on_mismatch: tag_auto_tag_errors
        tags:
          scene: "{scene}"
    """
    with open(template_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML template: expected dict, got {type(data)}")

    pattern = data.get("pattern", "")
    if not pattern:
        raise ValueError("YAML template missing 'pattern' field")

    # Parse options
    opts_data = data.get("options", {})
    options = TemplateOptions(
        case_insensitive=opts_data.get("case_insensitive", False),
        require_full_match=opts_data.get("require_full_match", True),
        on_mismatch=opts_data.get("on_mismatch", "skip_file"),
    )

    # Parse tag mapping (back-references)
    tag_mapping: dict[str, str] = {}
    tags_data = data.get("tags", {})
    for tag_path, ref in tags_data.items():
        tag_mapping[tag_path] = str(ref)

    # Parse pattern into segments
    segments = _parse_yaml_pattern(pattern)

    return TagTemplate(
        raw_template=pattern,
        segments=segments,
        options=options,
        tag_mapping=tag_mapping,
    )


def load_template_auto(directory: str) -> list[TagTemplate]:
    """Auto-detect and load templates from a directory.

    Looks for load_template.yaml first, then load_template.txt.
    Returns a list of TagTemplate objects (empty if no template found).
    """
    from pathlib import Path

    dir_path = Path(directory)

    # Prefer YAML format
    for yaml_name in ("load_template.yaml", "load_template.yml"):
        yaml_path = dir_path / yaml_name
        if yaml_path.exists():
            return [load_yaml_template(str(yaml_path))]

    # Fall back to txt format
    txt_path = dir_path / "load_template.txt"
    if txt_path.exists():
        return load_template_file(str(txt_path))

    return []
