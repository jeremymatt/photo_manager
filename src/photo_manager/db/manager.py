"""Database manager for Photo Manager."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from photo_manager.db.models import (
    DuplicateGroup,
    DuplicateGroupMember,
    ImageRecord,
    ImageTag,
    TagDefinition,
)
from photo_manager.db.schema import (
    CURRENT_SCHEMA_VERSION,
    DEFAULT_TAG_TREE,
    SCHEMA_V1,
)


class DatabaseManager:
    """Manages SQLite database for photo metadata and tags."""

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else None
        self._conn: sqlite3.Connection | None = None

    @property
    def db_path(self) -> Path | None:
        return self._db_path

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def create_database(self, db_path: str | Path) -> None:
        """Create a new database with schema and default tag tree."""
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA_V1)
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO schema_version (version, applied_date) VALUES (?, ?)",
            (CURRENT_SCHEMA_VERSION, now),
        )
        self._seed_default_tags()
        self._conn.commit()

    def open_database(self, db_path: str | Path) -> None:
        """Open an existing database and check schema version."""
        self._db_path = Path(db_path)
        if not self._db_path.exists():
            raise FileNotFoundError(f"Database not found: {self._db_path}")
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        version = self._get_schema_version()
        if version < CURRENT_SCHEMA_VERSION:
            self._apply_migrations(version)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Context manager for database transactions."""
        self._ensure_open()
        try:
            yield
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # --- Image CRUD ---

    def add_image(self, image: ImageRecord) -> int:
        """Add an image to the database. Returns the new image ID."""
        self._ensure_open()
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """INSERT INTO images (
                filepath, filename, file_size, width, height,
                datetime, year, month, day, hour, minute, second,
                latitude, longitude, has_lat_lon, city, town, state,
                phash_0, phash_90, dhash_0, dhash_90,
                favorite, to_delete, reviewed, auto_tag_errors,
                date_added, date_modified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                image.filepath, image.filename, image.file_size,
                image.width, image.height,
                image.datetime_str, image.year, image.month, image.day,
                image.hour, image.minute, image.second,
                image.latitude, image.longitude, int(image.has_lat_lon),
                image.city, image.town, image.state,
                image.phash_0, image.phash_90, image.dhash_0, image.dhash_90,
                int(image.favorite), int(image.to_delete),
                int(image.reviewed), int(image.auto_tag_errors),
                now, now,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_image(self, image_id: int) -> ImageRecord | None:
        """Get an image by ID."""
        self._ensure_open()
        row = self._conn.execute(
            "SELECT * FROM images WHERE id = ?", (image_id,)
        ).fetchone()
        return self._row_to_image(row) if row else None

    def get_image_by_path(self, filepath: str) -> ImageRecord | None:
        """Get an image by its filepath."""
        self._ensure_open()
        row = self._conn.execute(
            "SELECT * FROM images WHERE filepath = ?", (filepath,)
        ).fetchone()
        return self._row_to_image(row) if row else None

    def get_all_images(self, order_by: str = "filepath") -> list[ImageRecord]:
        """Get all images, optionally ordered."""
        self._ensure_open()
        valid_orders = {
            "filepath", "filename", "datetime", "year", "file_size",
            "date_added", "id",
        }
        if order_by not in valid_orders:
            order_by = "filepath"
        rows = self._conn.execute(
            f"SELECT * FROM images ORDER BY {order_by}"
        ).fetchall()
        return [self._row_to_image(row) for row in rows]

    def update_image(self, image: ImageRecord) -> None:
        """Update an existing image record."""
        self._ensure_open()
        if image.id is None:
            raise ValueError("Cannot update image without an ID")
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """UPDATE images SET
                filepath=?, filename=?, file_size=?, width=?, height=?,
                datetime=?, year=?, month=?, day=?, hour=?, minute=?, second=?,
                latitude=?, longitude=?, has_lat_lon=?, city=?, town=?, state=?,
                phash_0=?, phash_90=?, dhash_0=?, dhash_90=?,
                favorite=?, to_delete=?, reviewed=?, auto_tag_errors=?,
                date_modified=?
            WHERE id=?""",
            (
                image.filepath, image.filename, image.file_size,
                image.width, image.height,
                image.datetime_str, image.year, image.month, image.day,
                image.hour, image.minute, image.second,
                image.latitude, image.longitude, int(image.has_lat_lon),
                image.city, image.town, image.state,
                image.phash_0, image.phash_90, image.dhash_0, image.dhash_90,
                int(image.favorite), int(image.to_delete),
                int(image.reviewed), int(image.auto_tag_errors),
                now, image.id,
            ),
        )
        self._conn.commit()

    def delete_image(self, image_id: int) -> None:
        """Delete an image and its tag associations."""
        self._ensure_open()
        self._conn.execute("DELETE FROM images WHERE id = ?", (image_id,))
        self._conn.commit()

    def get_image_count(self) -> int:
        """Get total number of images in the database."""
        self._ensure_open()
        row = self._conn.execute("SELECT COUNT(*) FROM images").fetchone()
        return row[0]

    # --- Tag Definition CRUD ---

    def add_tag_definition(self, tag_def: TagDefinition) -> int:
        """Add a tag definition. Returns the new tag ID."""
        self._ensure_open()
        cursor = self._conn.execute(
            """INSERT INTO tag_definitions (name, parent_id, data_type, is_category)
            VALUES (?, ?, ?, ?)""",
            (tag_def.name, tag_def.parent_id, tag_def.data_type,
             int(tag_def.is_category)),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_tag_definition(self, tag_id: int) -> TagDefinition | None:
        """Get a tag definition by ID."""
        self._ensure_open()
        row = self._conn.execute(
            "SELECT * FROM tag_definitions WHERE id = ?", (tag_id,)
        ).fetchone()
        return self._row_to_tag_def(row) if row else None

    def get_tag_definition_by_name(
        self, name: str, parent_id: int | None = None
    ) -> TagDefinition | None:
        """Get a tag definition by name and optional parent."""
        self._ensure_open()
        if parent_id is None:
            row = self._conn.execute(
                "SELECT * FROM tag_definitions WHERE name = ? AND parent_id IS NULL",
                (name,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM tag_definitions WHERE name = ? AND parent_id = ?",
                (name, parent_id),
            ).fetchone()
        return self._row_to_tag_def(row) if row else None

    def get_all_tag_definitions(self) -> list[TagDefinition]:
        """Get all tag definitions."""
        self._ensure_open()
        rows = self._conn.execute(
            "SELECT * FROM tag_definitions ORDER BY id"
        ).fetchall()
        return [self._row_to_tag_def(row) for row in rows]

    def get_tag_children(self, parent_id: int | None = None) -> list[TagDefinition]:
        """Get child tag definitions of a parent (None for root tags)."""
        self._ensure_open()
        if parent_id is None:
            rows = self._conn.execute(
                "SELECT * FROM tag_definitions WHERE parent_id IS NULL ORDER BY name"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM tag_definitions WHERE parent_id = ? ORDER BY name",
                (parent_id,),
            ).fetchall()
        return [self._row_to_tag_def(row) for row in rows]

    def get_tag_tree(self) -> list[dict]:
        """Get the full tag tree as nested dicts.

        Returns a list of root nodes, each with a 'children' key.
        """
        all_tags = self.get_all_tag_definitions()
        by_parent: dict[int | None, list[TagDefinition]] = {}
        for tag in all_tags:
            by_parent.setdefault(tag.parent_id, []).append(tag)

        def build_subtree(parent_id: int | None) -> list[dict]:
            children = by_parent.get(parent_id, [])
            return [
                {
                    "tag": tag,
                    "children": build_subtree(tag.id),
                }
                for tag in children
            ]

        return build_subtree(None)

    def resolve_tag_path(self, dotted_path: str) -> TagDefinition | None:
        """Resolve a dotted tag path like 'event.birthday.Alice' to a TagDefinition."""
        parts = dotted_path.split(".")
        parent_id = None
        tag_def = None
        for part in parts:
            tag_def = self.get_tag_definition_by_name(part, parent_id)
            if tag_def is None:
                return None
            parent_id = tag_def.id
        return tag_def

    def get_tag_path(self, tag_id: int) -> str:
        """Build dotted path for a tag by walking the parent chain.

        Example: tag 'Alice' under 'birthday' under 'event' -> 'event.birthday.Alice'
        """
        parts: list[str] = []
        current = self.get_tag_definition(tag_id)
        while current:
            parts.append(current.name)
            if current.parent_id is not None:
                current = self.get_tag_definition(current.parent_id)
            else:
                current = None
        return ".".join(reversed(parts))

    def ensure_tag_path(
        self, dotted_path: str, leaf_data_type: str = "string"
    ) -> TagDefinition:
        """Resolve a dotted tag path, creating missing nodes.

        All new intermediate nodes are created as categories.
        If an existing leaf node gains a child, it is promoted to a category.
        Returns the leaf TagDefinition.
        """
        parts = dotted_path.split(".")
        parent_id: int | None = None
        tag_def: TagDefinition | None = None

        for i, part in enumerate(parts):
            tag_def = self.get_tag_definition_by_name(part, parent_id)
            is_leaf = (i == len(parts) - 1)

            if tag_def is None:
                # Create the missing node
                new_tag = TagDefinition(
                    name=part,
                    parent_id=parent_id,
                    data_type=leaf_data_type if is_leaf else "string",
                    is_category=not is_leaf,
                )
                new_id = self.add_tag_definition(new_tag)
                tag_def = self.get_tag_definition(new_id)
            elif not is_leaf and not tag_def.is_category:
                # Promote existing leaf to category since it's gaining children
                self._ensure_open()
                self._conn.execute(
                    "UPDATE tag_definitions SET is_category = 1 WHERE id = ?",
                    (tag_def.id,),
                )
                self._conn.commit()
                tag_def.is_category = True

            parent_id = tag_def.id

        return tag_def

    # --- Image Tag CRUD ---

    def set_image_tag(
        self, image_id: int, tag_id: int, value: str | None = None
    ) -> int:
        """Set a tag on an image. Returns the image_tag ID."""
        self._ensure_open()
        cursor = self._conn.execute(
            """INSERT OR IGNORE INTO image_tags (image_id, tag_id, value)
            VALUES (?, ?, ?)""",
            (image_id, tag_id, value),
        )
        self._conn.commit()
        return cursor.lastrowid

    def remove_image_tag(
        self, image_id: int, tag_id: int, value: str | None = None
    ) -> None:
        """Remove a tag from an image."""
        self._ensure_open()
        if value is None:
            self._conn.execute(
                "DELETE FROM image_tags WHERE image_id = ? AND tag_id = ?",
                (image_id, tag_id),
            )
        else:
            self._conn.execute(
                "DELETE FROM image_tags WHERE image_id = ? AND tag_id = ? AND value = ?",
                (image_id, tag_id, value),
            )
        self._conn.commit()

    def get_image_tags(self, image_id: int) -> list[ImageTag]:
        """Get all tags for an image."""
        self._ensure_open()
        rows = self._conn.execute(
            "SELECT * FROM image_tags WHERE image_id = ?", (image_id,)
        ).fetchall()
        return [
            ImageTag(id=r[0], image_id=r[1], tag_id=r[2], value=r[3])
            for r in rows
        ]

    def get_images_with_tag(
        self, tag_id: int, value: str | None = None
    ) -> list[ImageRecord]:
        """Get all images that have a specific tag (and optionally a specific value)."""
        self._ensure_open()
        if value is None:
            rows = self._conn.execute(
                """SELECT i.* FROM images i
                JOIN image_tags it ON i.id = it.image_id
                WHERE it.tag_id = ?""",
                (tag_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT i.* FROM images i
                JOIN image_tags it ON i.id = it.image_id
                WHERE it.tag_id = ? AND it.value = ?""",
                (tag_id, value),
            ).fetchall()
        return [self._row_to_image(row) for row in rows]

    # --- Duplicate Group CRUD ---

    def create_duplicate_group(self, image_ids: list[int]) -> int:
        """Create a duplicate group with the given image IDs. Returns group ID."""
        self._ensure_open()
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "INSERT INTO duplicate_groups (created_date) VALUES (?)", (now,)
        )
        group_id = cursor.lastrowid
        for image_id in image_ids:
            self._conn.execute(
                """INSERT INTO duplicate_group_members (group_id, image_id)
                VALUES (?, ?)""",
                (group_id, image_id),
            )
        self._conn.commit()
        return group_id

    def get_duplicate_groups(self) -> list[DuplicateGroup]:
        """Get all duplicate groups with their members."""
        self._ensure_open()
        groups = []
        group_rows = self._conn.execute(
            "SELECT * FROM duplicate_groups ORDER BY id"
        ).fetchall()
        for grow in group_rows:
            group = DuplicateGroup(id=grow[0], created_date=grow[1])
            member_rows = self._conn.execute(
                """SELECT * FROM duplicate_group_members
                WHERE group_id = ? ORDER BY id""",
                (group.id,),
            ).fetchall()
            group.members = [
                DuplicateGroupMember(
                    id=m[0], group_id=m[1], image_id=m[2],
                    is_kept=bool(m[3]), is_not_duplicate=bool(m[4]),
                )
                for m in member_rows
            ]
            groups.append(group)
        return groups

    def update_duplicate_member(
        self, member_id: int, is_kept: bool | None = None,
        is_not_duplicate: bool | None = None,
    ) -> None:
        """Update a duplicate group member's flags."""
        self._ensure_open()
        updates = []
        params: list[Any] = []
        if is_kept is not None:
            updates.append("is_kept = ?")
            params.append(int(is_kept))
        if is_not_duplicate is not None:
            updates.append("is_not_duplicate = ?")
            params.append(int(is_not_duplicate))
        if not updates:
            return
        params.append(member_id)
        self._conn.execute(
            f"UPDATE duplicate_group_members SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        self._conn.commit()

    def delete_duplicate_group(self, group_id: int) -> None:
        """Delete a duplicate group and its members."""
        self._ensure_open()
        self._conn.execute(
            "DELETE FROM duplicate_groups WHERE id = ?", (group_id,)
        )
        self._conn.commit()

    # --- Raw query support ---

    def execute_query(
        self, sql: str, params: tuple = ()
    ) -> list[sqlite3.Row]:
        """Execute a raw SQL query and return results."""
        self._ensure_open()
        self._conn.row_factory = sqlite3.Row
        try:
            return self._conn.execute(sql, params).fetchall()
        finally:
            self._conn.row_factory = None

    # --- Private helpers ---

    def _ensure_open(self) -> None:
        if self._conn is None:
            raise RuntimeError("Database is not open")

    def _get_schema_version(self) -> int:
        try:
            row = self._conn.execute(
                "SELECT MAX(version) FROM schema_version"
            ).fetchone()
            return row[0] if row and row[0] else 0
        except sqlite3.OperationalError:
            return 0

    def _apply_migrations(self, from_version: int) -> None:
        # Future migrations go here
        pass

    def _seed_default_tags(self) -> None:
        """Insert the default tag tree into a fresh database."""
        name_to_id: dict[tuple[str, int | None], int] = {}
        for name, parent_name, data_type, is_category in DEFAULT_TAG_TREE:
            parent_id = None
            if parent_name is not None:
                # Find the parent by scanning previous entries
                # Parent could be at root or nested, so we look up by name
                # and find the most recently inserted one
                candidates = [
                    v for k, v in name_to_id.items() if k[0] == parent_name
                ]
                if candidates:
                    parent_id = candidates[-1]

            cursor = self._conn.execute(
                """INSERT INTO tag_definitions (name, parent_id, data_type, is_category)
                VALUES (?, ?, ?, ?)""",
                (name, parent_id, data_type, int(is_category)),
            )
            name_to_id[(name, parent_id)] = cursor.lastrowid

    def _row_to_image(self, row: tuple) -> ImageRecord:
        return ImageRecord(
            id=row[0],
            filepath=row[1],
            filename=row[2],
            file_size=row[3],
            width=row[4],
            height=row[5],
            datetime_str=row[6],
            year=row[7],
            month=row[8],
            day=row[9],
            hour=row[10],
            minute=row[11],
            second=row[12],
            latitude=row[13],
            longitude=row[14],
            has_lat_lon=bool(row[15]),
            city=row[16],
            town=row[17],
            state=row[18],
            phash_0=row[19],
            phash_90=row[20],
            dhash_0=row[21],
            dhash_90=row[22],
            favorite=bool(row[23]),
            to_delete=bool(row[24]),
            reviewed=bool(row[25]),
            auto_tag_errors=bool(row[26]),
            date_added=row[27],
            date_modified=row[28],
        )

    def _row_to_tag_def(self, row: tuple) -> TagDefinition:
        return TagDefinition(
            id=row[0],
            name=row[1],
            parent_id=row[2],
            data_type=row[3],
            is_category=bool(row[4]),
        )
