"""Database schema definitions, migrations, and seed data."""

from __future__ import annotations

CURRENT_SCHEMA_VERSION = 4

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_size INTEGER,
    width INTEGER,
    height INTEGER,
    datetime TEXT,
    year INTEGER,
    month INTEGER,
    day INTEGER,
    hour INTEGER,
    minute INTEGER,
    second INTEGER,
    latitude TEXT,
    longitude TEXT,
    has_lat_lon INTEGER DEFAULT 0,
    city TEXT,
    town TEXT,
    state TEXT,
    phash_0 TEXT,
    phash_90 TEXT,
    phash_180 TEXT,
    phash_270 TEXT,
    dhash_0 TEXT,
    dhash_90 TEXT,
    dhash_180 TEXT,
    dhash_270 TEXT,
    phash_hmirror TEXT,
    dhash_hmirror TEXT,
    favorite INTEGER DEFAULT 0,
    to_delete INTEGER DEFAULT 0,
    reviewed INTEGER DEFAULT 0,
    auto_tag_errors INTEGER DEFAULT 0,
    date_added TEXT,
    date_modified TEXT,
    UNIQUE(filepath)
);

CREATE TABLE IF NOT EXISTS tag_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES tag_definitions(id),
    data_type TEXT DEFAULT 'string',
    is_category INTEGER DEFAULT 0,
    UNIQUE(name, parent_id)
);

CREATE TABLE IF NOT EXISTS image_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tag_definitions(id),
    UNIQUE(image_id, tag_id)
);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_date TEXT
);

CREATE TABLE IF NOT EXISTS duplicate_group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES duplicate_groups(id) ON DELETE CASCADE,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    is_kept INTEGER DEFAULT 0,
    is_not_duplicate INTEGER DEFAULT 0,
    UNIQUE(group_id, image_id)
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_date TEXT
);

CREATE INDEX IF NOT EXISTS idx_images_filepath ON images(filepath);
CREATE INDEX IF NOT EXISTS idx_images_year ON images(year);
CREATE INDEX IF NOT EXISTS idx_images_datetime ON images(datetime);
CREATE INDEX IF NOT EXISTS idx_images_favorite ON images(favorite);
CREATE INDEX IF NOT EXISTS idx_images_to_delete ON images(to_delete);
CREATE INDEX IF NOT EXISTS idx_images_reviewed ON images(reviewed);
CREATE INDEX IF NOT EXISTS idx_image_tags_image ON image_tags(image_id);
CREATE INDEX IF NOT EXISTS idx_image_tags_tag ON image_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_tag_definitions_parent ON tag_definitions(parent_id);
CREATE INDEX IF NOT EXISTS idx_duplicate_members_group ON duplicate_group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_duplicate_members_image ON duplicate_group_members(image_id);
"""

MIGRATION_V1_TO_V2 = """
ALTER TABLE images ADD COLUMN phash_180 TEXT;
ALTER TABLE images ADD COLUMN phash_270 TEXT;
ALTER TABLE images ADD COLUMN dhash_180 TEXT;
ALTER TABLE images ADD COLUMN dhash_270 TEXT;
"""

MIGRATION_V2_TO_V3 = """
ALTER TABLE images ADD COLUMN phash_hmirror TEXT;
ALTER TABLE images ADD COLUMN dhash_hmirror TEXT;
"""

# Default tag tree: (name, parent_name_or_None, data_type, is_category)
# Entries are ordered so parents come before children.
DEFAULT_TAG_TREE: list[tuple[str, str | None, str, bool]] = [
    # Root-level categories/tags
    ("favorite", None, "bool", False),
    ("to_delete", None, "bool", False),
    ("photographer_name", None, "string", False),
    ("reviewed", None, "bool", False),
    ("auto_tag_errors", None, "bool", False),

    # Scene
    ("scene", None, "string", True),
    ("indoor", "scene", "string", False),
    ("outdoor", "scene", "string", True),
    ("lake", "outdoor", "string", False),
    ("hike", "outdoor", "string", False),

    # Event
    ("event", None, "string", True),
    ("christmas", "event", "string", False),
    ("birthday", "event", "string", True),
    ("alice", "birthday", "string", False),
    ("bob", "birthday", "string", False),
    ("vacation", "event", "string", True),
    ("lake", "vacation", "string", False),
    ("city", "vacation", "string", False),

    # Person
    ("person", None, "string", True),
    ("alice", "person", "string", False),
    ("bob", "person", "string", False),

    # Datetime
    ("datetime", None, "datetime", True),
    ("datetime_value", "datetime", "datetime", False),
    ("year", "datetime", "int", False),
    ("month", "datetime", "int", False),
    ("day", "datetime", "int", False),
    ("hr", "datetime", "int", False),
    ("min", "datetime", "int", False),
    ("sec", "datetime", "int", False),

    # Location
    ("location", None, "string", True),
    ("latitude", "location", "string", False),
    ("longitude", "location", "string", False),
    ("has_lat_lon", "location", "bool", False),
    ("city", "location", "string", False),
    ("town", "location", "string", False),
    ("state", "location", "string", False),

    # Image size
    ("image_size", None, "int", True),
    ("width", "image_size", "int", False),
    ("height", "image_size", "int", False),
]
