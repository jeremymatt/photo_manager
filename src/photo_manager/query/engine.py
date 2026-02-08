"""Query engine that translates parsed AST to SQL and executes queries."""

from __future__ import annotations

from typing import Any

from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import ImageRecord
from photo_manager.query.parser import (
    ASTNode,
    ComparisonNode,
    LogicalNode,
    parse_query,
)

# Tag paths that map directly to columns on the images table
FIXED_FIELD_MAP: dict[str, str] = {
    "favorite": "favorite",
    "to_delete": "to_delete",
    "reviewed": "reviewed",
    "auto_tag_errors": "auto_tag_errors",
    "datetime": "datetime",
    "datetime.year": "year",
    "datetime.month": "month",
    "datetime.day": "day",
    "datetime.hr": "hour",
    "datetime.min": "minute",
    "datetime.sec": "second",
    "location.latitude": "latitude",
    "location.longitude": "longitude",
    "location.has_lat_lon": "has_lat_lon",
    "location.city": "city",
    "location.town": "town",
    "location.state": "state",
    "image_size.width": "width",
    "image_size.height": "height",
}

SQL_OPERATORS: dict[str, str] = {
    "==": "=",
    "!=": "!=",
    ">": ">",
    ">=": ">=",
    "<": "<",
    "<=": "<=",
}


class QueryEngine:
    """Execute tag queries against the database."""

    def __init__(self, db: DatabaseManager):
        self._db = db
        self._join_counter = 0

    def query(self, expression: str) -> list[ImageRecord]:
        """Parse and execute a query expression, returning matching images."""
        ast = parse_query(expression)
        sql, params = self.to_sql(ast)
        rows = self._db.execute_query(sql, tuple(params))
        # Convert Row objects back to tuples for _row_to_image
        return [
            self._db._row_to_image(tuple(row))
            for row in rows
        ]

    def to_sql(self, ast: ASTNode) -> tuple[str, list[Any]]:
        """Convert an AST to a SQL query.

        Returns (sql_string, params_list).
        """
        self._join_counter = 0
        where_clause, params, joins = self._node_to_sql(ast)
        join_str = " ".join(joins)
        sql = f"SELECT DISTINCT i.* FROM images i {join_str} WHERE {where_clause}"
        return sql, params

    def _node_to_sql(
        self, node: ASTNode
    ) -> tuple[str, list[Any], list[str]]:
        """Recursively convert an AST node to SQL components.

        Returns (where_clause, params, joins).
        """
        if isinstance(node, LogicalNode):
            left_where, left_params, left_joins = self._node_to_sql(node.left)
            right_where, right_params, right_joins = self._node_to_sql(node.right)

            sql_op = "AND" if node.operator == "&&" else "OR"
            where = f"({left_where} {sql_op} {right_where})"
            return where, left_params + right_params, left_joins + right_joins

        if isinstance(node, ComparisonNode):
            return self._comparison_to_sql(node)

        raise ValueError(f"Unknown AST node type: {type(node)}")

    def _comparison_to_sql(
        self, node: ComparisonNode
    ) -> tuple[str, list[Any], list[str]]:
        """Convert a comparison node to SQL."""
        tag_path = node.tag_path
        sql_op = SQL_OPERATORS.get(node.operator)
        if sql_op is None:
            raise ValueError(f"Unknown operator: {node.operator}")

        # Check if this maps to a fixed column
        if tag_path in FIXED_FIELD_MAP:
            column = FIXED_FIELD_MAP[tag_path]
            value = self._convert_value(node.value, column)
            where = f"i.{column} {sql_op} ?"
            return where, [value], []

        # Dynamic tag query - need to join to image_tags and tag_definitions
        self._join_counter += 1
        alias_it = f"it{self._join_counter}"
        alias_td = f"td{self._join_counter}"

        # Resolve the tag path to find the tag definition
        # The tag_path could be like "person", "event.birthday", "scene.outdoor"
        parts = tag_path.split(".")

        joins = [
            f"JOIN image_tags {alias_it} ON i.id = {alias_it}.image_id",
            f"JOIN tag_definitions {alias_td} ON {alias_it}.tag_id = {alias_td}.id",
        ]

        if len(parts) == 1:
            # Simple tag: tag.person == "Alice"
            # Match tag name, compare value
            where = f"({alias_td}.name = ? AND {alias_it}.value {sql_op} ?)"
            params = [parts[0], str(node.value)]
        elif len(parts) == 2:
            # Nested tag: tag.event.birthday or tag.scene.outdoor
            # Could be: parent_name.child_name == value
            # We need to match the child tag under the parent
            self._join_counter += 1
            alias_parent = f"td{self._join_counter}"
            joins.append(
                f"JOIN tag_definitions {alias_parent} "
                f"ON {alias_td}.parent_id = {alias_parent}.id"
            )
            where = (
                f"({alias_parent}.name = ? AND {alias_td}.name = ? "
                f"AND {alias_it}.value {sql_op} ?)"
            )
            params = [parts[0], parts[1], str(node.value)]
        else:
            # Deeper nesting - build a chain of parent joins
            # For now, handle up to 3 levels
            where_parts = [f"{alias_td}.name = ?"]
            params = [parts[-1]]

            current_alias = alias_td
            for i in range(len(parts) - 2, -1, -1):
                self._join_counter += 1
                parent_alias = f"td{self._join_counter}"
                joins.append(
                    f"JOIN tag_definitions {parent_alias} "
                    f"ON {current_alias}.parent_id = {parent_alias}.id"
                )
                where_parts.append(f"{parent_alias}.name = ?")
                params.append(parts[i])
                current_alias = parent_alias

            where_parts.append(f"{alias_it}.value {sql_op} ?")
            params.append(str(node.value))
            where = f"({' AND '.join(where_parts)})"

        return where, params, joins

    def _convert_value(self, value: Any, column: str) -> Any:
        """Convert a query value to the appropriate type for a column."""
        bool_columns = {
            "favorite", "to_delete", "reviewed",
            "auto_tag_errors", "has_lat_lon",
        }
        int_columns = {
            "year", "month", "day", "hour", "minute", "second",
            "width", "height",
        }
        if column in bool_columns:
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, str):
                return 1 if value.lower() in ("true", "1", "yes") else 0
            return int(bool(value))
        if column in int_columns:
            return int(value)
        return value
