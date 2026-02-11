"""Tests for the query parser and engine."""

import pytest

from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import ImageRecord
from photo_manager.query.engine import QueryEngine
from photo_manager.query.parser import (
    ComparisonNode,
    LogicalNode,
    NegationNode,
    PresenceNode,
    QueryParseError,
    parse_query,
)


class TestQueryParser:
    # --- Presence checks ---

    def test_presence_check(self):
        ast = parse_query("tag.person.alice")
        assert isinstance(ast, PresenceNode)
        assert ast.tag_path == "person.alice"
        assert ast.wildcard is None

    def test_presence_single_level(self):
        ast = parse_query("tag.favorite")
        assert isinstance(ast, PresenceNode)
        assert ast.tag_path == "favorite"

    def test_tag_ref_lowercased(self):
        ast = parse_query("tag.Person.Alice")
        assert isinstance(ast, PresenceNode)
        assert ast.tag_path == "person.alice"

    # --- Comparisons (fixed fields) ---

    def test_numeric_comparison(self):
        ast = parse_query("tag.datetime.year>=2018")
        assert isinstance(ast, ComparisonNode)
        assert ast.tag_path == "datetime.year"
        assert ast.operator == ">="
        assert ast.value == 2018

    def test_boolean_comparison(self):
        ast = parse_query("tag.favorite==true")
        assert isinstance(ast, ComparisonNode)
        assert ast.value is True

    def test_gt_comparison(self):
        ast = parse_query("tag.datetime.year>2020")
        assert isinstance(ast, ComparisonNode)
        assert ast.operator == ">"
        assert ast.value == 2020

    def test_not_equal(self):
        ast = parse_query("tag.datetime.year!=2020")
        assert isinstance(ast, ComparisonNode)
        assert ast.operator == "!="

    def test_none_value(self):
        ast = parse_query("tag.datetime.year==None")
        assert isinstance(ast, ComparisonNode)
        assert ast.value is None
        assert ast.operator == "=="

    def test_none_not_equal(self):
        ast = parse_query("tag.datetime.year!=None")
        assert isinstance(ast, ComparisonNode)
        assert ast.value is None
        assert ast.operator == "!="

    # --- Backward compat: comparison on dynamic tags ---

    def test_backward_compat_string_comparison(self):
        """tag.person==\"alice\" should still parse as ComparisonNode."""
        ast = parse_query('tag.person=="alice"')
        assert isinstance(ast, ComparisonNode)
        assert ast.tag_path == "person"
        assert ast.operator == "=="
        assert ast.value == "alice"

    # --- Negation ---

    def test_negation_presence(self):
        ast = parse_query("!tag.person.alice")
        assert isinstance(ast, NegationNode)
        assert isinstance(ast.child, PresenceNode)
        assert ast.child.tag_path == "person.alice"

    def test_negation_grouped(self):
        ast = parse_query("!(tag.person.alice && tag.scene.outdoor)")
        assert isinstance(ast, NegationNode)
        assert isinstance(ast.child, LogicalNode)
        assert ast.child.operator == "&&"

    def test_negation_boolean(self):
        ast = parse_query("!tag.favorite")
        assert isinstance(ast, NegationNode)
        assert isinstance(ast.child, PresenceNode)
        assert ast.child.tag_path == "favorite"

    # --- Wildcards ---

    def test_wildcard_inclusive(self):
        ast = parse_query("tag.scene.outdoor*")
        assert isinstance(ast, PresenceNode)
        assert ast.tag_path == "scene.outdoor"
        assert ast.wildcard == "inclusive"

    def test_wildcard_children_only(self):
        ast = parse_query("tag.scene.outdoor.*")
        assert isinstance(ast, PresenceNode)
        assert ast.tag_path == "scene.outdoor"
        assert ast.wildcard == "children_only"

    # --- Logical operators ---

    def test_and_expression(self):
        ast = parse_query("tag.person.alice && tag.scene.outdoor")
        assert isinstance(ast, LogicalNode)
        assert ast.operator == "&&"
        assert isinstance(ast.left, PresenceNode)
        assert isinstance(ast.right, PresenceNode)

    def test_or_expression(self):
        ast = parse_query("tag.scene.indoor || tag.scene.outdoor")
        assert isinstance(ast, LogicalNode)
        assert ast.operator == "||"

    def test_nested_parentheses(self):
        ast = parse_query(
            "(tag.person.alice || tag.person.bob) && tag.scene.outdoor"
        )
        assert isinstance(ast, LogicalNode)
        assert ast.operator == "&&"
        assert isinstance(ast.left, LogicalNode)
        assert ast.left.operator == "||"

    def test_mixed_query(self):
        ast = parse_query(
            "tag.person.alice && tag.datetime.year>=2020 && !tag.scene.indoor"
        )
        assert isinstance(ast, LogicalNode)

    # --- Error cases ---

    def test_unterminated_string_raises(self):
        with pytest.raises(QueryParseError):
            parse_query('tag.person=="Alice')

    def test_missing_value_raises(self):
        with pytest.raises(QueryParseError):
            parse_query("tag.person==")

    def test_single_quotes(self):
        ast = parse_query("tag.person=='alice'")
        assert isinstance(ast, ComparisonNode)
        assert ast.value == "alice"


class TestQueryEngine:
    @pytest.fixture
    def db_with_data(self, tmp_path):
        db = DatabaseManager()
        db.create_database(tmp_path / "query_test.db")

        # Add test images
        id1 = db.add_image(ImageRecord(
            filepath="alice_bday.jpg", filename="alice_bday.jpg",
            year=2019, favorite=True,
        ))
        id2 = db.add_image(ImageRecord(
            filepath="bob_vacation.jpg", filename="bob_vacation.jpg",
            year=2020, favorite=False,
        ))
        id3 = db.add_image(ImageRecord(
            filepath="alice_vacation.jpg", filename="alice_vacation.jpg",
            year=2019, favorite=True,
        ))
        id4 = db.add_image(ImageRecord(
            filepath="no_year.jpg", filename="no_year.jpg",
            year=None, favorite=False,
        ))

        # Tag images with presence-based tags
        alice_tag = db.ensure_tag_path("person.alice")
        bob_tag = db.ensure_tag_path("person.bob")
        bday_tag = db.ensure_tag_path("event.birthday")
        vacation_tag = db.ensure_tag_path("event.vacation")
        indoor_tag = db.ensure_tag_path("scene.indoor")
        outdoor_tag = db.resolve_tag_path("scene.outdoor")
        lake_tag = db.resolve_tag_path("scene.outdoor.lake")

        db.set_image_tag(id1, alice_tag.id)
        db.set_image_tag(id1, bday_tag.id)
        db.set_image_tag(id1, indoor_tag.id)

        db.set_image_tag(id2, bob_tag.id)
        db.set_image_tag(id2, vacation_tag.id)
        db.set_image_tag(id2, outdoor_tag.id)
        db.set_image_tag(id2, lake_tag.id)

        db.set_image_tag(id3, alice_tag.id)
        db.set_image_tag(id3, vacation_tag.id)

        yield db
        db.close()

    # --- Fixed field queries ---

    def test_query_fixed_field(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query("tag.datetime.year>=2019")
        assert len(results) == 3

    def test_query_fixed_field_specific(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query("tag.datetime.year==2020")
        assert len(results) == 1
        assert results[0].filepath == "bob_vacation.jpg"

    def test_query_boolean_field(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query("tag.favorite==true")
        assert len(results) == 2

    def test_query_not_equal(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query("tag.datetime.year!=2020")
        assert len(results) == 2  # 2019 images (no_year has NULL)

    # --- Presence queries ---

    def test_query_presence(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query("tag.person.alice")
        assert len(results) == 2

    def test_query_presence_nested(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query("tag.event.vacation")
        assert len(results) == 2

    def test_query_presence_combined(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query(
            "tag.person.alice && tag.event.vacation"
        )
        assert len(results) == 1
        assert results[0].filepath == "alice_vacation.jpg"

    def test_query_or(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query(
            "tag.event.birthday || tag.event.vacation"
        )
        assert len(results) == 3

    # --- Boolean shorthand ---

    def test_query_boolean_shorthand(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query("tag.favorite")
        assert len(results) == 2

    def test_query_negated_boolean(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query("!tag.favorite")
        assert len(results) == 2  # bob_vacation + no_year

    # --- Negation ---

    def test_query_negation(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query("!tag.person.alice")
        # Images without alice tag: bob_vacation, no_year
        assert len(results) == 2

    def test_query_negation_grouped(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query(
            "!(tag.person.alice && tag.event.birthday)"
        )
        # Everything except alice_bday
        assert len(results) == 3

    # --- None / IS NULL ---

    def test_query_none(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query("tag.datetime.year==None")
        assert len(results) == 1
        assert results[0].filepath == "no_year.jpg"

    def test_query_not_none(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query("tag.datetime.year!=None")
        assert len(results) == 3

    # --- Wildcard queries ---

    def test_query_wildcard_inclusive(self, db_with_data):
        engine = QueryEngine(db_with_data)
        # outdoor* should match images with outdoor OR any child (lake, hike)
        results = engine.query("tag.scene.outdoor*")
        assert len(results) == 1  # bob_vacation has outdoor + lake

    def test_query_wildcard_children_only(self, db_with_data):
        engine = QueryEngine(db_with_data)
        # outdoor.* should match images with lake or hike but NOT outdoor itself
        results = engine.query("tag.scene.outdoor.*")
        assert len(results) == 1  # bob_vacation has lake

    # --- Backward compat ---

    def test_backward_compat_string_eq(self, db_with_data):
        engine = QueryEngine(db_with_data)
        # Old-style query: tag.person=="alice" → presence check for person.alice
        results = engine.query('tag.person=="alice"')
        assert len(results) == 2

    def test_backward_compat_string_neq(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query('tag.person!="alice"')
        assert len(results) == 2  # bob_vacation + no_year

    # --- Mixed queries ---

    def test_mixed_query(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query(
            "tag.person.alice && tag.datetime.year>=2019 && !tag.scene.indoor"
        )
        assert len(results) == 1
        assert results[0].filepath == "alice_vacation.jpg"

    # --- SQL generation ---

    def test_to_sql_fixed(self, db_with_data):
        engine = QueryEngine(db_with_data)
        ast = parse_query("tag.datetime.year>=2018")
        sql, params = engine.to_sql(ast)
        assert "SELECT DISTINCT i.* FROM images i" in sql
        assert "i.year >= ?" in sql
        assert params == [2018]

    def test_to_sql_presence(self, db_with_data):
        engine = QueryEngine(db_with_data)
        ast = parse_query("tag.person.alice")
        sql, params = engine.to_sql(ast)
        assert "EXISTS" in sql
        assert "person" in params
        assert "alice" in params
