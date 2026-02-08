"""Tests for the query parser and engine."""

import pytest

from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import ImageRecord
from photo_manager.query.engine import QueryEngine
from photo_manager.query.parser import (
    ComparisonNode,
    LogicalNode,
    QueryParseError,
    parse_query,
)


class TestQueryParser:
    def test_simple_comparison(self):
        ast = parse_query('tag.person=="Alice"')
        assert isinstance(ast, ComparisonNode)
        assert ast.tag_path == "person"
        assert ast.operator == "=="
        assert ast.value == "Alice"

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

    def test_and_expression(self):
        ast = parse_query('tag.person=="Alice" && tag.event=="birthday"')
        assert isinstance(ast, LogicalNode)
        assert ast.operator == "&&"
        assert isinstance(ast.left, ComparisonNode)
        assert isinstance(ast.right, ComparisonNode)

    def test_or_expression(self):
        ast = parse_query('tag.scene=="indoor" || tag.scene=="outdoor"')
        assert isinstance(ast, LogicalNode)
        assert ast.operator == "||"

    def test_nested_parentheses(self):
        ast = parse_query(
            '(tag.person=="Alice" || tag.person=="Bob") && tag.event=="birthday"'
        )
        assert isinstance(ast, LogicalNode)
        assert ast.operator == "&&"
        assert isinstance(ast.left, LogicalNode)
        assert ast.left.operator == "||"

    def test_complex_expression(self):
        ast = parse_query(
            '((tag.person=="Alice" || tag.person=="Bob") '
            '&& tag.person!="Carol" && tag.event=="birthday") '
            "&& tag.datetime.year>=2018"
        )
        assert isinstance(ast, LogicalNode)

    def test_not_equal(self):
        ast = parse_query('tag.scene!="outdoor"')
        assert isinstance(ast, ComparisonNode)
        assert ast.operator == "!="

    def test_unterminated_string_raises(self):
        with pytest.raises(QueryParseError):
            parse_query('tag.person=="Alice')

    def test_missing_value_raises(self):
        with pytest.raises(QueryParseError):
            parse_query("tag.person==")

    def test_single_quotes(self):
        ast = parse_query("tag.person=='Alice'")
        assert isinstance(ast, ComparisonNode)
        assert ast.value == "Alice"


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

        # Tag images
        person_tag = db.resolve_tag_path("person")
        event_tag = db.resolve_tag_path("event")

        db.set_image_tag(id1, person_tag.id, "Alice")
        db.set_image_tag(id1, event_tag.id, "birthday")
        db.set_image_tag(id2, person_tag.id, "Bob")
        db.set_image_tag(id2, event_tag.id, "vacation")
        db.set_image_tag(id3, person_tag.id, "Alice")
        db.set_image_tag(id3, event_tag.id, "vacation")

        yield db
        db.close()

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

    def test_query_dynamic_tag(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query('tag.person=="Alice"')
        assert len(results) == 2

    def test_query_combined(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query(
            'tag.person=="Alice" && tag.event=="vacation"'
        )
        assert len(results) == 1
        assert results[0].filepath == "alice_vacation.jpg"

    def test_query_or(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query(
            'tag.event=="birthday" || tag.event=="vacation"'
        )
        assert len(results) == 3

    def test_query_not_equal(self, db_with_data):
        engine = QueryEngine(db_with_data)
        results = engine.query("tag.datetime.year!=2020")
        assert len(results) == 2

    def test_to_sql(self, db_with_data):
        engine = QueryEngine(db_with_data)
        ast = parse_query("tag.datetime.year>=2018")
        sql, params = engine.to_sql(ast)
        assert "SELECT DISTINCT i.* FROM images i" in sql
        assert "i.year >= ?" in sql
        assert params == [2018]
