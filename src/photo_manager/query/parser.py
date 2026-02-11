"""Query expression parser for tag-based image filtering.

Parses expressions like:
    tag.person.alice && tag.datetime.year>=2018
    tag.scene.indoor || tag.scene.outdoor
    tag.favorite
    !tag.scene.indoor
    !(tag.person.alice && tag.outdoor.hike)
    tag.outdoor.hike*          (hike + all descendants)
    tag.outdoor.hike.*         (descendants only, not hike itself)
    tag.datetime.year==None    (missing value)

Grammar:
    expression  = or_expr
    or_expr     = and_expr ('||' and_expr)*
    and_expr    = unary ('&&' unary)*
    unary       = '!' unary | atom
    atom        = '(' expression ')'
                | tag_ref OPERATOR value    (comparison for fixed fields)
                | tag_ref                   (presence check for dynamic tags)
    tag_ref     = 'tag.' dotted_name
    value       = QUOTED_STRING | NUMBER | BOOLEAN | NONE
    OPERATOR    = '==' | '!=' | '>' | '>=' | '<' | '<='
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


class TokenType(Enum):
    TAG_REF = auto()       # tag.person, tag.datetime.year
    STRING = auto()        # "Alice", 'Alice'
    NUMBER = auto()        # 2018, 3.14
    BOOLEAN = auto()       # true, false
    NONE = auto()          # None
    OP_EQ = auto()         # ==
    OP_NEQ = auto()        # !=
    OP_GT = auto()         # >
    OP_GTE = auto()        # >=
    OP_LT = auto()         # <
    OP_LTE = auto()        # <=
    OP_AND = auto()        # &&
    OP_OR = auto()         # ||
    OP_NOT = auto()        # !
    WILDCARD = auto()      # *
    LPAREN = auto()        # (
    RPAREN = auto()        # )
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: Any
    pos: int


class Tokenizer:
    """Tokenize a query expression string."""

    def __init__(self, text: str):
        self._text = text
        self._pos = 0

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while self._pos < len(self._text):
            self._skip_whitespace()
            if self._pos >= len(self._text):
                break

            ch = self._text[self._pos]

            if ch == "(":
                tokens.append(Token(TokenType.LPAREN, "(", self._pos))
                self._pos += 1
            elif ch == ")":
                tokens.append(Token(TokenType.RPAREN, ")", self._pos))
                self._pos += 1
            elif ch == "*":
                tokens.append(Token(TokenType.WILDCARD, "*", self._pos))
                self._pos += 1
            elif ch == "&" and self._peek(1) == "&":
                tokens.append(Token(TokenType.OP_AND, "&&", self._pos))
                self._pos += 2
            elif ch == "|" and self._peek(1) == "|":
                tokens.append(Token(TokenType.OP_OR, "||", self._pos))
                self._pos += 2
            elif ch == "=" and self._peek(1) == "=":
                tokens.append(Token(TokenType.OP_EQ, "==", self._pos))
                self._pos += 2
            elif ch == "!" and self._peek(1) == "=":
                tokens.append(Token(TokenType.OP_NEQ, "!=", self._pos))
                self._pos += 2
            elif ch == "!":
                tokens.append(Token(TokenType.OP_NOT, "!", self._pos))
                self._pos += 1
            elif ch == ">" and self._peek(1) == "=":
                tokens.append(Token(TokenType.OP_GTE, ">=", self._pos))
                self._pos += 2
            elif ch == "<" and self._peek(1) == "=":
                tokens.append(Token(TokenType.OP_LTE, "<=", self._pos))
                self._pos += 2
            elif ch == ">":
                tokens.append(Token(TokenType.OP_GT, ">", self._pos))
                self._pos += 1
            elif ch == "<":
                tokens.append(Token(TokenType.OP_LT, "<", self._pos))
                self._pos += 1
            elif ch in ('"', "'"):
                tokens.append(self._read_string(ch))
            elif ch == "t" and self._text[self._pos:self._pos + 4] == "tag.":
                tokens.append(self._read_tag_ref())
            elif ch == "t" and self._text[self._pos:self._pos + 4] == "true":
                tokens.append(Token(TokenType.BOOLEAN, True, self._pos))
                self._pos += 4
            elif ch == "f" and self._text[self._pos:self._pos + 5] == "false":
                tokens.append(Token(TokenType.BOOLEAN, False, self._pos))
                self._pos += 5
            elif ch == "N" and self._text[self._pos:self._pos + 4] == "None":
                tokens.append(Token(TokenType.NONE, None, self._pos))
                self._pos += 4
            elif ch.isdigit() or (ch == "-" and self._pos + 1 < len(self._text) and self._text[self._pos + 1].isdigit()):
                tokens.append(self._read_number())
            else:
                raise QueryParseError(
                    f"Unexpected character '{ch}' at position {self._pos}"
                )

        tokens.append(Token(TokenType.EOF, None, self._pos))
        return tokens

    def _peek(self, offset: int) -> str:
        pos = self._pos + offset
        return self._text[pos] if pos < len(self._text) else ""

    def _skip_whitespace(self) -> None:
        while self._pos < len(self._text) and self._text[self._pos].isspace():
            self._pos += 1

    def _read_string(self, quote: str) -> Token:
        start = self._pos
        self._pos += 1  # skip opening quote
        chars: list[str] = []
        while self._pos < len(self._text) and self._text[self._pos] != quote:
            chars.append(self._text[self._pos])
            self._pos += 1
        if self._pos >= len(self._text):
            raise QueryParseError(f"Unterminated string at position {start}")
        self._pos += 1  # skip closing quote
        return Token(TokenType.STRING, "".join(chars), start)

    def _read_tag_ref(self) -> Token:
        start = self._pos
        self._pos += 4  # skip 'tag.'
        chars: list[str] = []
        while self._pos < len(self._text) and (
            self._text[self._pos].isalnum()
            or self._text[self._pos] in (".", "_")
        ):
            chars.append(self._text[self._pos])
            self._pos += 1
        # Keep trailing dot in value (signals children-only wildcard when
        # followed by '>').  The parser handles stripping it.
        return Token(TokenType.TAG_REF, "".join(chars).lower(), start)

    def _read_number(self) -> Token:
        start = self._pos
        chars: list[str] = []
        if self._text[self._pos] == "-":
            chars.append("-")
            self._pos += 1
        has_dot = False
        while self._pos < len(self._text) and (
            self._text[self._pos].isdigit() or self._text[self._pos] == "."
        ):
            if self._text[self._pos] == ".":
                if has_dot:
                    break
                has_dot = True
            chars.append(self._text[self._pos])
            self._pos += 1
        value_str = "".join(chars)
        value: int | float = float(value_str) if has_dot else int(value_str)
        return Token(TokenType.NUMBER, value, start)


# --- AST Nodes ---

@dataclass
class ComparisonNode:
    """A comparison like tag.datetime.year >= 2018."""
    tag_path: str       # e.g. "datetime.year", "favorite"
    operator: str       # ==, !=, >, >=, <, <=
    value: Any          # string, number, boolean, or None


@dataclass
class LogicalNode:
    """A logical combination of expressions."""
    operator: str       # "&&" or "||"
    left: ASTNode
    right: ASTNode


@dataclass
class PresenceNode:
    """Check if a tag exists on an image (presence-based)."""
    tag_path: str                 # e.g. "person.alice", "favorite"
    wildcard: str | None = None   # None, "inclusive" (*), "children_only" (.*)


@dataclass
class NegationNode:
    """Negate an expression."""
    child: ASTNode


ASTNode = ComparisonNode | LogicalNode | PresenceNode | NegationNode


class QueryParseError(Exception):
    """Error raised when parsing a query expression fails."""
    pass


_VALUE_TOKENS = {TokenType.STRING, TokenType.NUMBER, TokenType.BOOLEAN, TokenType.NONE}

_COMPARISON_OPS = {
    TokenType.OP_EQ, TokenType.OP_NEQ,
    TokenType.OP_GT, TokenType.OP_GTE,
    TokenType.OP_LT, TokenType.OP_LTE,
}


class Parser:
    """Parse tokens into an AST."""

    def __init__(self, tokens: list[Token]):
        self._tokens = tokens
        self._pos = 0

    def parse(self) -> ASTNode:
        node = self._parse_or()
        if self._current().type != TokenType.EOF:
            raise QueryParseError(
                f"Unexpected token '{self._current().value}' "
                f"at position {self._current().pos}"
            )
        return node

    def _parse_or(self) -> ASTNode:
        left = self._parse_and()
        while self._current().type == TokenType.OP_OR:
            self._advance()
            right = self._parse_and()
            left = LogicalNode(operator="||", left=left, right=right)
        return left

    def _parse_and(self) -> ASTNode:
        left = self._parse_unary()
        while self._current().type == TokenType.OP_AND:
            self._advance()
            right = self._parse_unary()
            left = LogicalNode(operator="&&", left=left, right=right)
        return left

    def _parse_unary(self) -> ASTNode:
        if self._current().type == TokenType.OP_NOT:
            self._advance()  # skip !
            child = self._parse_unary()  # recursive for !!x
            return NegationNode(child=child)
        return self._parse_atom()

    def _parse_atom(self) -> ASTNode:
        token = self._current()

        if token.type == TokenType.LPAREN:
            self._advance()  # skip (
            node = self._parse_or()
            if self._current().type != TokenType.RPAREN:
                raise QueryParseError(
                    f"Expected ')' at position {self._current().pos}"
                )
            self._advance()  # skip )
            return node

        if token.type == TokenType.TAG_REF:
            return self._parse_tag_expression()

        raise QueryParseError(
            f"Unexpected token '{token.value}' at position {token.pos}"
        )

    def _parse_tag_expression(self) -> ASTNode:
        """Parse a tag reference followed by optional operator+value or wildcard."""
        tag_token = self._advance()
        tag_path = tag_token.value  # already lowercased
        next_token = self._current()

        # Check for comparison operators
        if next_token.type in _COMPARISON_OPS:
            return self._parse_comparison_tail(tag_path)

        # Handle * wildcard: tag.hike* (inclusive) or tag.hike.* (children_only)
        if next_token.type == TokenType.WILDCARD:
            self._advance()  # consume *
            # Check for children-only (.*) vs inclusive (*)
            if tag_path.endswith("."):
                return PresenceNode(
                    tag_path=tag_path.rstrip("."),
                    wildcard="children_only",
                )
            return PresenceNode(tag_path=tag_path, wildcard="inclusive")

        # No operator — bare presence check
        # Strip any trailing dot (shouldn't normally occur without >)
        clean_path = tag_path.rstrip(".")
        return PresenceNode(tag_path=clean_path)

    def _parse_comparison_tail(self, tag_path: str) -> ComparisonNode:
        """Parse operator + value after a tag reference."""
        # Strip trailing dot from tag path (if any)
        tag_path = tag_path.rstrip(".")

        op_token = self._advance()
        if op_token.type not in _COMPARISON_OPS:
            raise QueryParseError(
                f"Expected comparison operator at position {op_token.pos}"
            )

        val_token = self._current()
        if val_token.type not in _VALUE_TOKENS:
            raise QueryParseError(
                f"Expected value at position {val_token.pos}"
            )
        self._advance()

        return ComparisonNode(
            tag_path=tag_path,
            operator=op_token.value,
            value=val_token.value,
        )

    def _current(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _peek_token(self, offset: int) -> Token:
        idx = self._pos + offset
        if idx < len(self._tokens):
            return self._tokens[idx]
        return self._tokens[-1]  # EOF


def parse_query(expression: str) -> ASTNode:
    """Parse a query expression string into an AST.

    Examples:
        ast = parse_query('tag.person.alice && tag.datetime.year>=2018')
        ast = parse_query('!tag.scene.indoor')
        ast = parse_query('tag.outdoor.hike*')
    """
    tokenizer = Tokenizer(expression)
    tokens = tokenizer.tokenize()
    parser = Parser(tokens)
    return parser.parse()
