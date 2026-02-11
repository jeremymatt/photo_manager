"""Query engine that translates parsed AST to SQL and executes queries."""

from __future__ import annotations

from typing import Any

from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import ImageRecord
from photo_manager.query.parser import (
    ASTNode,
    ComparisonNode,
    LogicalNode,
    NegationNode,
    PresenceNode,
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

_BOOL_FIELDS = {
    "favorite", "to_delete", "reviewed",
    "auto_tag_errors", "has_lat_lon",
}

_INT_FIELDS = {
    "year", "month", "day", "hour", "minute", "second",
    "width", "height",
}


class QueryEngine:
    """Execute tag queries against the database."""

    def __init__(self, db: DatabaseManager):
        self._db = db
        self._subquery_counter = 0

    def query(self, expression: str) -> list[ImageRecord]:
        """Parse and execute a query expression, returning matching images."""
        ast = parse_query(expression)
        sql, params = self.to_sql(ast)
        rows = self._db.execute_query(sql, tuple(params))
        return [self._db._row_to_image(row) for row in rows]

    def to_sql(self, ast: ASTNode) -> tuple[str, list[Any]]:
        """Convert an AST to a SQL query.

        Returns (sql_string, params_list).
        """
        self._subquery_counter = 0
        where_clause, params = self._node_to_sql(ast)
        sql = f"SELECT DISTINCT i.* FROM images i WHERE {where_clause}"
        return sql, params

    def _node_to_sql(self, node: ASTNode) -> tuple[str, list[Any]]:
        """Recursively convert an AST node to SQL components.

        Returns (where_clause, params).
        """
        if isinstance(node, LogicalNode):
            left_where, left_params = self._node_to_sql(node.left)
            right_where, right_params = self._node_to_sql(node.right)
            sql_op = "AND" if node.operator == "&&" else "OR"
            where = f"({left_where} {sql_op} {right_where})"
            return where, left_params + right_params

        if isinstance(node, NegationNode):
            return self._negation_to_sql(node)

        if isinstance(node, PresenceNode):
            return self._presence_to_sql(node)

        if isinstance(node, ComparisonNode):
            return self._comparison_to_sql(node)

        raise ValueError(f"Unknown AST node type: {type(node)}")

    def _negation_to_sql(
        self, node: NegationNode
    ) -> tuple[str, list[Any]]:
        """Convert a negation node to SQL."""
        child_where, child_params = self._node_to_sql(node.child)
        return f"NOT ({child_where})", child_params

    def _presence_to_sql(
        self, node: PresenceNode
    ) -> tuple[str, list[Any]]:
        """Convert a presence check to SQL."""
        tag_path = node.tag_path

        # Fixed boolean fields: presence means ==true
        if tag_path in FIXED_FIELD_MAP:
            column = FIXED_FIELD_MAP[tag_path]
            if column in _BOOL_FIELDS:
                return f"i.{column} = 1", []
            # Non-boolean fixed fields: presence means IS NOT NULL
            return f"i.{column} IS NOT NULL", []

        # Dynamic tag — use EXISTS subquery
        if node.wildcard:
            return self._wildcard_presence_to_sql(node)

        return self._tag_exists_sql(tag_path)

    def _wildcard_presence_to_sql(
        self, node: PresenceNode
    ) -> tuple[str, list[Any]]:
        """Convert a wildcard presence check to SQL using descendant tag IDs."""
        tag_def = self._db.resolve_tag_path(node.tag_path)
        if tag_def is None or tag_def.id is None:
            # Tag doesn't exist — no matches possible
            return "0", []

        include_self = node.wildcard == "inclusive"
        tag_ids = self._db.get_descendant_tag_ids(
            tag_def.id, include_self=include_self
        )
        if not tag_ids:
            return "0", []

        self._subquery_counter += 1
        alias = f"wit{self._subquery_counter}"
        placeholders = ", ".join("?" for _ in tag_ids)
        sql = (
            f"EXISTS (SELECT 1 FROM image_tags {alias} "
            f"WHERE {alias}.image_id = i.id "
            f"AND {alias}.tag_id IN ({placeholders}))"
        )
        return sql, list(tag_ids)

    def _tag_exists_sql(
        self, tag_path: str
    ) -> tuple[str, list[Any]]:
        """Generate EXISTS subquery for a dynamic tag presence check."""
        parts = tag_path.split(".")
        self._subquery_counter += 1
        alias_it = f"eit{self._subquery_counter}"
        alias_td = f"etd{self._subquery_counter}"

        if len(parts) == 1:
            sql = (
                f"EXISTS (SELECT 1 FROM image_tags {alias_it} "
                f"JOIN tag_definitions {alias_td} ON {alias_it}.tag_id = {alias_td}.id "
                f"WHERE {alias_it}.image_id = i.id AND {alias_td}.name = ?)"
            )
            return sql, [parts[0]]

        if len(parts) == 2:
            self._subquery_counter += 1
            alias_parent = f"etd{self._subquery_counter}"
            sql = (
                f"EXISTS (SELECT 1 FROM image_tags {alias_it} "
                f"JOIN tag_definitions {alias_td} ON {alias_it}.tag_id = {alias_td}.id "
                f"JOIN tag_definitions {alias_parent} ON {alias_td}.parent_id = {alias_parent}.id "
                f"WHERE {alias_it}.image_id = i.id "
                f"AND {alias_parent}.name = ? AND {alias_td}.name = ?)"
            )
            return sql, [parts[0], parts[1]]

        # Deeper nesting — chain parent joins
        joins = [
            f"JOIN tag_definitions {alias_td} ON {alias_it}.tag_id = {alias_td}.id"
        ]
        where_parts = [f"{alias_td}.name = ?"]
        params = [parts[-1]]

        current_alias = alias_td
        for i in range(len(parts) - 2, -1, -1):
            self._subquery_counter += 1
            parent_alias = f"etd{self._subquery_counter}"
            joins.append(
                f"JOIN tag_definitions {parent_alias} "
                f"ON {current_alias}.parent_id = {parent_alias}.id"
            )
            where_parts.append(f"{parent_alias}.name = ?")
            params.append(parts[i])
            current_alias = parent_alias

        join_str = " ".join(joins)
        where_str = " AND ".join(where_parts)
        sql = (
            f"EXISTS (SELECT 1 FROM image_tags {alias_it} "
            f"{join_str} "
            f"WHERE {alias_it}.image_id = i.id AND {where_str})"
        )
        return sql, params

    def _comparison_to_sql(
        self, node: ComparisonNode
    ) -> tuple[str, list[Any]]:
        """Convert a comparison node to SQL."""
        tag_path = node.tag_path
        sql_op = SQL_OPERATORS.get(node.operator)
        if sql_op is None:
            raise ValueError(f"Unknown operator: {node.operator}")

        # Check if this maps to a fixed column
        if tag_path in FIXED_FIELD_MAP:
            column = FIXED_FIELD_MAP[tag_path]

            # Handle None (IS NULL / IS NOT NULL)
            if node.value is None:
                if node.operator == "==":
                    return f"i.{column} IS NULL", []
                elif node.operator == "!=":
                    return f"i.{column} IS NOT NULL", []
                else:
                    raise ValueError(
                        f"Operator '{node.operator}' not supported with None"
                    )

            value = self._convert_value(node.value, column)
            where = f"i.{column} {sql_op} ?"
            return where, [value]

        # Dynamic tag comparison — backward compat: treat as presence check
        # tag.person=="alice" → presence check for person.alice
        if isinstance(node.value, str):
            composed_path = f"{tag_path}.{node.value.lower()}"
            if node.operator == "==":
                return self._tag_exists_sql(composed_path)
            elif node.operator == "!=":
                exists_sql, params = self._tag_exists_sql(composed_path)
                return f"NOT ({exists_sql})", params

        # For non-string values on dynamic tags, try presence with value as path segment
        composed_path = f"{tag_path}.{str(node.value).lower()}"
        if node.operator == "==":
            return self._tag_exists_sql(composed_path)
        elif node.operator == "!=":
            exists_sql, params = self._tag_exists_sql(composed_path)
            return f"NOT ({exists_sql})", params

        # Other operators on dynamic tags don't make sense in presence model
        raise ValueError(
            f"Operator '{node.operator}' not supported for dynamic tags. "
            f"Use fixed fields (datetime.year, etc.) for comparison queries."
        )

    def _convert_value(self, value: Any, column: str) -> Any:
        """Convert a query value to the appropriate type for a column."""
        if column in _BOOL_FIELDS:
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, str):
                return 1 if value.lower() in ("true", "1", "yes") else 0
            return int(bool(value))
        if column in _INT_FIELDS:
            return int(value)
        return value
