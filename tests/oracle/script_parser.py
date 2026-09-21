"""Parse SQL*Plus catalog scripts into executable SQL and PL/SQL statements."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SQLPLUS_CMD = re.compile(
    r"^(SET|PROMPT|TTITLE|BTITLE|BREAK|COMPUTE|WHENEVER|SPOOL|EXIT|QUIT|PAUSE|ACCEPT|HOST|SHOW|CONNECT|DISCONNECT|UNDEFINE|CLEAR|REPHEADER|REPFOOTER|STORE|SAVE|GET|START|RUN|LIST|DEL|INPUT|CHANGE|APPEND|EDIT|PRINT|REM)\b",
    re.IGNORECASE,
)
_COLUMN_NEW_VALUE = re.compile(
    r"^(?:COLUMN|COL)\s+(\w+)\s+NEW_VALUE\s+(\w+)\b",
    re.IGNORECASE,
)
_COLUMN_CMD = re.compile(r"^(?:COLUMN|COL)\b", re.IGNORECASE)
_VARIABLE_CMD = re.compile(
    r"^(?:VARIABLE|VAR)\s+(\w+)\s+(\S+)",
    re.IGNORECASE,
)
_DEFINE_CMD = re.compile(
    r"^DEFINE\s+(\w+)\s*=\s*(.*)$",
    re.IGNORECASE,
)
_EXEC_CMD = re.compile(r"^(?:EXEC|EXECUTE)\s+(.+)$", re.IGNORECASE)
_SLASH_LINE = re.compile(r"^/\s*$")
_KEYWORD = re.compile(r"[A-Za-z]+")
_POSITIONAL = re.compile(r"&&?(\d+)")
_NAMED_DEFINE = re.compile(r"&&?([A-Za-z_][A-Za-z0-9_]*)")
_PLSQL_CREATE = re.compile(
    r"^CREATE\b.*\b(PACKAGE|PROCEDURE|FUNCTION|TRIGGER|TYPE\s+BODY)\b",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class ParsedScript:
    """SQL and PL/SQL remaining after SQL*Plus client commands are removed.

    Attributes:
        statements (list[str]): Executable statements in file order.
        new_values (dict[str, str]): SELECT alias (upper) to SQL*Plus define name.
        variables (dict[str, str]): Bind name (upper) to VARIABLE type text.
        defines (dict[str, str]): DEFINE name (upper) to literal value.
    """

    statements: list[str]
    new_values: dict[str, str] = field(default_factory=dict)
    variables: dict[str, str] = field(default_factory=dict)
    defines: dict[str, str] = field(default_factory=dict)


def parse_sqlplus_script(text: str) -> ParsedScript:
    """Strip SQL*Plus formatting commands and split remaining statements.

    Args:
        text (str): Raw catalog `.sql` file contents.

    Returns:
        ParsedScript: Statements plus NEW_VALUE, VARIABLE, and DEFINE metadata.
    """
    new_values: dict[str, str] = {}
    variables: dict[str, str] = {}
    defines: dict[str, str] = {}
    statements: list[str] = []
    buffer: list[str] = []
    in_block_comment = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            continue
        if not buffer and not stripped:
            continue
        if not buffer and stripped.startswith("/*") and "*/" not in stripped:
            in_block_comment = True
            continue
        if not buffer and stripped.startswith("/*") and stripped.endswith("*/"):
            continue
        if not buffer and stripped.startswith("--"):
            continue
        if not buffer and _SLASH_LINE.match(stripped):
            continue
        if not buffer:
            new_value_match = _COLUMN_NEW_VALUE.match(stripped)
            if new_value_match:
                new_values[new_value_match.group(1).upper()] = new_value_match.group(2)
                continue
            if _COLUMN_CMD.match(stripped) or _SQLPLUS_CMD.match(stripped):
                continue
            variable_match = _VARIABLE_CMD.match(stripped)
            if variable_match:
                variables[variable_match.group(1).upper()] = variable_match.group(2)
                continue
            define_match = _DEFINE_CMD.match(stripped)
            if define_match:
                defines[define_match.group(1).upper()] = define_match.group(2).strip().strip("\"'")
                continue
            exec_match = _EXEC_CMD.match(stripped)
            if exec_match:
                statements.append(f"BEGIN\n{exec_match.group(1).rstrip(';')};\nEND;")
                continue
        if _SLASH_LINE.match(stripped) and buffer:
            statements.append(_flush_buffer(buffer))
            continue
        buffer.append(line)
        candidate = "\n".join(buffer)
        if not _is_plsql(candidate) and _sql_complete(candidate):
            statements.append(_flush_buffer(buffer))

    if buffer and "".join(buffer).strip():
        statements.append(_flush_buffer(buffer))

    return ParsedScript(
        statements=[item for item in statements if item],
        new_values=new_values,
        variables=variables,
        defines=defines,
    )


def apply_substitutions(sql: str, args: list[str], defines: dict[str, str]) -> str:
    """Replace SQL*Plus positional and named substitution variables.

    Missing positional arguments become empty strings. Named defines are
    matched case-insensitively.

    Args:
        sql (str): Statement text that may contain `&1` or `&&name`.
        args (list[str]): Values for `&1`, `&2`, ... (index 0 is `&1`).
        defines (dict[str, str]): Named SQL*Plus defines keyed by upper-case name.

    Returns:
        str: Statement with substitutions applied.
    """

    def replace_positional(match: re.Match[str]) -> str:
        index = int(match.group(1)) - 1
        if 0 <= index < len(args):
            return args[index]
        return ""

    replaced = _POSITIONAL.sub(replace_positional, sql)

    def replace_named(match: re.Match[str]) -> str:
        name = match.group(1).upper()
        return defines.get(name, "")

    return _NAMED_DEFINE.sub(replace_named, replaced)


def _flush_buffer(buffer: list[str]) -> str:
    """Join and clear the statement buffer.

    Args:
        buffer (list[str]): Accumulated statement lines.

    Returns:
        str: Stripped statement without a trailing slash or semicolon.
    """
    text = "\n".join(buffer).strip()
    buffer.clear()
    if not _is_plsql(text) and text.endswith(";"):
        text = text[:-1].rstrip()
    return text


def _is_plsql(text: str) -> bool:
    """Return True when the statement must be terminated with a slash.

    Args:
        text (str): Accumulated statement text.

    Returns:
        bool: True for anonymous blocks and stored PL/SQL units.
    """
    keywords = _leading_keywords(text, limit=8)
    if not keywords:
        return False
    if keywords[0] in {"DECLARE", "BEGIN"}:
        return True
    return bool(_PLSQL_CREATE.match(text))


def _leading_keywords(text: str, limit: int) -> list[str]:
    """Return the first SQL keywords in a statement, skipping comments.

    Args:
        text (str): Accumulated statement text.
        limit (int): Maximum keywords to collect.

    Returns:
        list[str]: Upper-case keywords in order of appearance.
    """
    keywords: list[str] = []
    for token in _KEYWORD.findall(_strip_leading_comments(text)):
        keywords.append(token.upper())
        if len(keywords) >= limit:
            break
    return keywords


def _strip_leading_comments(text: str) -> str:
    """Remove leading `--` and `/* */` comments so the first keyword is visible.

    Args:
        text (str): Accumulated statement text.

    Returns:
        str: Text with a leading comment prefix removed.
    """
    remaining = text.lstrip()
    while remaining:
        if remaining.startswith("--"):
            newline = remaining.find("\n")
            remaining = remaining[newline + 1 :].lstrip() if newline >= 0 else ""
            continue
        if remaining.startswith("/*"):
            end = remaining.find("*/")
            remaining = remaining[end + 2 :].lstrip() if end >= 0 else ""
            continue
        break
    return remaining


def _sql_complete(text: str) -> bool:
    """Return True when a non-PL/SQL statement ends with a semicolon.

    Semicolons inside quotes or comments are ignored.

    Args:
        text (str): Accumulated statement text.

    Returns:
        bool: True if the scanner is in default state and the last non-space char is `;`.
    """
    last_code = _last_unquoted_char(text)
    return last_code == ";"


def _last_unquoted_char(text: str) -> str | None:
    """Return the last non-whitespace character outside quotes and comments.

    Args:
        text (str): Accumulated statement text.

    Returns:
        str | None: Last significant character, or None when none exist.
    """
    last: str | None = None
    i = 0
    length = len(text)
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    while i < length:
        char = text[i]
        nxt = text[i + 1] if i + 1 < length else ""
        if in_line_comment:
            if char == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if char == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_single:
            if char == "'" and nxt == "'":
                i += 2
                continue
            if char == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if char == '"':
                in_double = False
            i += 1
            continue
        if char == "-" and nxt == "-":
            in_line_comment = True
            i += 2
            continue
        if char == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if char == "'":
            in_single = True
            i += 1
            continue
        if char == '"':
            in_double = True
            i += 1
            continue
        if not char.isspace():
            last = char
        i += 1
    if in_single or in_double or in_block_comment:
        return None
    return last
