"""Query expression parser for tag-based image filtering.

Parses expressions like:
    (tag.person=="Alice" && tag.event=="birthday" && tag.datetime.year>=2018)
    (tag.scene=="indoor" || tag.scene.outdoor=="lake")
    (tag.favorite==true)

Grammar:
    expression  = or_expr
    or_expr     = and_expr ('||' and_expr)*
    and_expr    = comparison ('&&' comparison)*
    comparison  = '(' expression ')'
                | tag_ref OPERATOR value
    tag_ref     = 'tag.' dotted_name
    value       = QUOTED_STRING | NUMBER | BOOLEAN
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
    OP_EQ = auto()         # ==
    OP_NEQ = auto()        # !=
    OP_GT = auto()         # >
    OP_GTE = auto()        # >=
    OP_LT = auto()         # <
    OP_LTE = auto()        # <=
    OP_AND = auto()        # &&
    OP_OR = auto()         # ||
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
        return Token(TokenType.TAG_REF, "".join(chars), start)

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
    """A comparison like tag.person == "Alice"."""
    tag_path: str       # e.g. "person", "datetime.year", "scene.outdoor"
    operator: str       # ==, !=, >, >=, <, <=
    value: Any          # string, number, or boolean


@dataclass
class LogicalNode:
    """A logical combination of expressions."""
    operator: str       # "&&" or "||"
    left: ASTNode
    right: ASTNode


ASTNode = ComparisonNode | LogicalNode


class QueryParseError(Exception):
    """Error raised when parsing a query expression fails."""
    pass


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
        left = self._parse_primary()
        while self._current().type == TokenType.OP_AND:
            self._advance()
            right = self._parse_primary()
            left = LogicalNode(operator="&&", left=left, right=right)
        return left

    def _parse_primary(self) -> ASTNode:
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
            return self._parse_comparison()

        raise QueryParseError(
            f"Unexpected token '{token.value}' at position {token.pos}"
        )

    def _parse_comparison(self) -> ComparisonNode:
        tag_token = self._current()
        if tag_token.type != TokenType.TAG_REF:
            raise QueryParseError(
                f"Expected tag reference at position {tag_token.pos}"
            )
        self._advance()

        op_token = self._current()
        if op_token.type not in (
            TokenType.OP_EQ, TokenType.OP_NEQ,
            TokenType.OP_GT, TokenType.OP_GTE,
            TokenType.OP_LT, TokenType.OP_LTE,
        ):
            raise QueryParseError(
                f"Expected comparison operator at position {op_token.pos}"
            )
        self._advance()

        val_token = self._current()
        if val_token.type not in (
            TokenType.STRING, TokenType.NUMBER, TokenType.BOOLEAN
        ):
            raise QueryParseError(
                f"Expected value at position {val_token.pos}"
            )
        self._advance()

        return ComparisonNode(
            tag_path=tag_token.value,
            operator=op_token.value,
            value=val_token.value,
        )

    def _current(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        token = self._tokens[self._pos]
        self._pos += 1
        return token


def parse_query(expression: str) -> ASTNode:
    """Parse a query expression string into an AST.

    Example:
        ast = parse_query('tag.person=="Alice" && tag.datetime.year>=2018')
    """
    tokenizer = Tokenizer(expression)
    tokens = tokenizer.tokenize()
    parser = Parser(tokens)
    return parser.parse()
