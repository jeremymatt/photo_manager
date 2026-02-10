"""Tests for DatabaseManager."""

import pytest

from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import ImageRecord, TagDefinition, ImageTag


@pytest.fixture
def db(tmp_path):
    """Create a fresh database for each test."""
    db_path = tmp_path / "test.db"
    manager = DatabaseManager()
    manager.create_database(db_path)
    yield manager
    manager.close()


class TestDatabaseCreation:
    def test_create_database(self, db):
        assert db.is_open
        assert db.db_path.exists()

    def test_default_tag_tree_seeded(self, db):
        tags = db.get_all_tag_definitions()
        assert len(tags) > 0
        names = [t.name for t in tags]
        assert "favorite" in names
        assert "person" in names
        assert "event" in names
        assert "scene" in names
        assert "datetime" in names

    def test_tag_tree_structure(self, db):
        # Check that birthday is a child of event
        event = db.get_tag_definition_by_name("event")
        assert event is not None
        assert event.is_category

        birthday = db.get_tag_definition_by_name("birthday", event.id)
        assert birthday is not None

        alice = db.get_tag_definition_by_name("Alice", birthday.id)
        assert alice is not None

    def test_resolve_tag_path(self, db):
        tag = db.resolve_tag_path("event.birthday.Alice")
        assert tag is not None
        assert tag.name == "Alice"

        tag = db.resolve_tag_path("datetime.year")
        assert tag is not None
        assert tag.data_type == "int"

        tag = db.resolve_tag_path("nonexistent.path")
        assert tag is None

    def test_open_existing_database(self, tmp_path):
        db_path = tmp_path / "test.db"
        db1 = DatabaseManager()
        db1.create_database(db_path)
        db1.close()

        db2 = DatabaseManager()
        db2.open_database(db_path)
        assert db2.is_open
        tags = db2.get_all_tag_definitions()
        assert len(tags) > 0
        db2.close()

    def test_open_nonexistent_raises(self, tmp_path):
        db = DatabaseManager()
        with pytest.raises(FileNotFoundError):
            db.open_database(tmp_path / "nope.db")


class TestImageCRUD:
    def test_add_and_get_image(self, db):
        img = ImageRecord(
            filepath="photos/test.jpg",
            filename="test.jpg",
            width=1920,
            height=1080,
        )
        img_id = db.add_image(img)
        assert img_id is not None

        retrieved = db.get_image(img_id)
        assert retrieved is not None
        assert retrieved.filepath == "photos/test.jpg"
        assert retrieved.width == 1920

    def test_get_image_by_path(self, db):
        img = ImageRecord(filepath="photos/a.jpg", filename="a.jpg")
        db.add_image(img)

        retrieved = db.get_image_by_path("photos/a.jpg")
        assert retrieved is not None
        assert retrieved.filename == "a.jpg"

    def test_update_image(self, db):
        img = ImageRecord(filepath="photos/b.jpg", filename="b.jpg")
        img_id = db.add_image(img)

        img = db.get_image(img_id)
        img.width = 3840
        img.favorite = True
        db.update_image(img)

        updated = db.get_image(img_id)
        assert updated.width == 3840
        assert updated.favorite is True

    def test_delete_image(self, db):
        img = ImageRecord(filepath="photos/c.jpg", filename="c.jpg")
        img_id = db.add_image(img)
        db.delete_image(img_id)

        assert db.get_image(img_id) is None

    def test_get_all_images(self, db):
        for i in range(3):
            db.add_image(ImageRecord(
                filepath=f"photos/{i}.jpg", filename=f"{i}.jpg"
            ))
        images = db.get_all_images()
        assert len(images) == 3

    def test_image_count(self, db):
        assert db.get_image_count() == 0
        db.add_image(ImageRecord(filepath="x.jpg", filename="x.jpg"))
        assert db.get_image_count() == 1

    def test_duplicate_filepath_rejected(self, db):
        db.add_image(ImageRecord(filepath="dup.jpg", filename="dup.jpg"))
        with pytest.raises(Exception):
            db.add_image(ImageRecord(filepath="dup.jpg", filename="dup.jpg"))


class TestImageTags:
    def test_set_and_get_tags(self, db):
        img_id = db.add_image(ImageRecord(
            filepath="tagged.jpg", filename="tagged.jpg"
        ))
        person_tag = db.resolve_tag_path("person")
        assert person_tag is not None

        db.set_image_tag(img_id, person_tag.id, "Alice")
        tags = db.get_image_tags(img_id)
        assert len(tags) == 1
        assert tags[0].value == "Alice"

    def test_remove_tag(self, db):
        img_id = db.add_image(ImageRecord(
            filepath="tagged2.jpg", filename="tagged2.jpg"
        ))
        person_tag = db.resolve_tag_path("person")
        db.set_image_tag(img_id, person_tag.id, "Bob")
        db.remove_image_tag(img_id, person_tag.id, "Bob")

        tags = db.get_image_tags(img_id)
        assert len(tags) == 0

    def test_get_images_with_tag(self, db):
        person_tag = db.resolve_tag_path("person")
        id1 = db.add_image(ImageRecord(filepath="a.jpg", filename="a.jpg"))
        id2 = db.add_image(ImageRecord(filepath="b.jpg", filename="b.jpg"))
        db.set_image_tag(id1, person_tag.id, "Alice")
        db.set_image_tag(id2, person_tag.id, "Bob")

        alice_images = db.get_images_with_tag(person_tag.id, "Alice")
        assert len(alice_images) == 1
        assert alice_images[0].filepath == "a.jpg"


class TestDuplicateGroups:
    def test_create_and_get_groups(self, db):
        id1 = db.add_image(ImageRecord(filepath="d1.jpg", filename="d1.jpg"))
        id2 = db.add_image(ImageRecord(filepath="d2.jpg", filename="d2.jpg"))

        group_id = db.create_duplicate_group([id1, id2])
        groups = db.get_duplicate_groups()
        assert len(groups) == 1
        assert len(groups[0].members) == 2

    def test_update_duplicate_member(self, db):
        id1 = db.add_image(ImageRecord(filepath="d3.jpg", filename="d3.jpg"))
        id2 = db.add_image(ImageRecord(filepath="d4.jpg", filename="d4.jpg"))

        db.create_duplicate_group([id1, id2])
        groups = db.get_duplicate_groups()
        member = groups[0].members[0]

        db.update_duplicate_member(member.id, is_kept=True)
        groups = db.get_duplicate_groups()
        assert groups[0].members[0].is_kept is True

    def test_delete_group(self, db):
        id1 = db.add_image(ImageRecord(filepath="d5.jpg", filename="d5.jpg"))
        id2 = db.add_image(ImageRecord(filepath="d6.jpg", filename="d6.jpg"))
        group_id = db.create_duplicate_group([id1, id2])

        db.delete_duplicate_group(group_id)
        groups = db.get_duplicate_groups()
        assert len(groups) == 0


class TestTagTree:
    def test_get_tag_tree(self, db):
        tree = db.get_tag_tree()
        assert len(tree) > 0
        # Find event node
        event_node = next(n for n in tree if n["tag"].name == "event")
        assert len(event_node["children"]) > 0

    def test_get_tag_children(self, db):
        event = db.get_tag_definition_by_name("event")
        children = db.get_tag_children(event.id)
        child_names = [c.name for c in children]
        assert "birthday" in child_names
        assert "vacation" in child_names

    def test_add_custom_tag(self, db):
        person = db.resolve_tag_path("person")
        new_tag = TagDefinition(
            name="Carol", parent_id=person.id, data_type="string"
        )
        tag_id = db.add_tag_definition(new_tag)
        assert tag_id is not None

        carol = db.get_tag_definition_by_name("Carol", person.id)
        assert carol is not None

    def test_get_tag_path(self, db):
        # event.birthday.Alice exists in default tree
        alice = db.resolve_tag_path("event.birthday.Alice")
        assert alice is not None
        path = db.get_tag_path(alice.id)
        assert path == "event.birthday.Alice"

        # Root-level tag
        event = db.resolve_tag_path("event")
        assert db.get_tag_path(event.id) == "event"

    def test_ensure_tag_path_existing(self, db):
        # Should return existing tag without creating anything
        alice = db.resolve_tag_path("event.birthday.Alice")
        result = db.ensure_tag_path("event.birthday.Alice")
        assert result.id == alice.id

    def test_ensure_tag_path_creates_intermediates(self, db):
        # Create entirely new path
        result = db.ensure_tag_path("weather.sunny")
        assert result is not None
        assert result.name == "sunny"
        assert not result.is_category

        # Verify intermediate was created as category
        weather = db.resolve_tag_path("weather")
        assert weather is not None
        assert weather.is_category

        # Verify full path resolves
        assert db.resolve_tag_path("weather.sunny") is not None

    def test_ensure_tag_path_promotes_leaf_to_category(self, db):
        # Alice under person is a leaf
        alice = db.resolve_tag_path("person.Alice")
        assert not alice.is_category

        # Adding a child should promote it to category
        db.ensure_tag_path("person.Alice.portrait")
        alice_after = db.resolve_tag_path("person.Alice")
        assert alice_after.is_category

        # The child should exist
        portrait = db.resolve_tag_path("person.Alice.portrait")
        assert portrait is not None
        assert not portrait.is_category


class TestPartialDatetime:
    def test_set_full_datetime(self):
        rec = ImageRecord()
        rec.set_partial_datetime(2018, 7, 15, 10, 30, 45)
        assert rec.datetime_str == "2018-07-15T10:30:45"
        assert rec.year == 2018
        assert rec.month == 7
        assert rec.day == 15
        assert rec.hour == 10

    def test_year_only(self):
        rec = ImageRecord()
        rec.set_partial_datetime(year=2020)
        assert rec.datetime_str == "2020-01-01T00:00:00"
        assert rec.year == 2020
        assert rec.month is None
        assert rec.day is None
        assert rec.hour is None

    def test_year_month(self):
        rec = ImageRecord()
        rec.set_partial_datetime(year=2020, month=6)
        assert rec.datetime_str == "2020-06-01T00:00:00"
        assert rec.year == 2020
        assert rec.month == 6
        assert rec.day is None

    def test_no_year_clears_all(self):
        rec = ImageRecord()
        rec.set_datetime(__import__("datetime").datetime(2020, 1, 1))
        rec.set_partial_datetime()
        assert rec.datetime_str is None
        assert rec.year is None
        assert rec.month is None

    def test_year_month_day_with_time(self):
        rec = ImageRecord()
        rec.set_partial_datetime(year=2021, month=12, day=25, hour=14)
        assert rec.datetime_str == "2021-12-25T14:00:00"
        assert rec.hour == 14
        assert rec.minute is None
