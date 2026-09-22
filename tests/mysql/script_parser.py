"""Parse MySQL catalog scripts, validating metadata headers and splitting statements."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field


class ScriptMetadata(BaseModel):
    """Metadata extracted from the boxed header of a catalog script.

    Attributes:
        script_name (str): The filename declared in the header.
        title (str): The website heading.
        tags (list[str]): Comma-separated category tags.
        purpose (str): One-line summary of what the script does.
        description (str): Multi-line explanation.
        parameters (str): Documented parameters or None.
        required_privileges (str): Privileges required to execute the script.
        output_format (str): Expected columns or output description.
        example_usage (str): Sample command line invocation.
        author (str): Author attribution line.
    """

    model_config = ConfigDict(extra="forbid")

    script_name: str
    title: str
    tags: list[str] = Field(default_factory=list)
    purpose: str = ""
    description: str = ""
    parameters: str = ""
    required_privileges: str = ""
    output_format: str = ""
    example_usage: str = ""
    author: str = ""


class ParsedMySQLScript(BaseModel):
    """Parsed representation of a MySQL catalog SQL file.

    Attributes:
        metadata (ScriptMetadata | None): Header metadata if found.
        statements (list[str]): Cleaned, executable SQL statements in order.
    """

    model_config = ConfigDict(extra="forbid")

    metadata: ScriptMetadata | None = None
    statements: list[str] = Field(default_factory=list)


_HEADER_PATTERN = re.compile(
    r"/\*+\s*\n(?P<header_content>.*?)\s*\*+/",
    re.DOTALL,
)


def parse_header_metadata(text: str) -> ScriptMetadata | None:
    """Extract metadata fields from the leading boxed comment header.

    Args:
        text (str): Raw SQL script contents.

    Returns:
        ScriptMetadata | None: Extracted metadata or None if no valid header exists.
    """
    match = _HEADER_PATTERN.search(text)
    if not match:
        return None

    content = match.group("header_content")
    fields: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for raw_line in content.splitlines():
        # Strip leading asterisks and whitespace
        clean_line = re.sub(r"^\s*\*?\s?", "", raw_line)
        key_match = re.match(r"^([A-Za-z ]+):\s*(.*)$", clean_line)
        if key_match:
            if current_key is not None:
                fields[current_key] = "\n".join(current_lines).strip()
            current_key = key_match.group(1).strip().lower().replace(" ", "_")
            current_lines = [key_match.group(2)]
        elif current_key is not None:
            current_lines.append(clean_line)

    if current_key is not None:
        fields[current_key] = "\n".join(current_lines).strip()

    script_name = fields.get("script_name", "")
    title = fields.get("title", "")
    tags_raw = fields.get("tags", "")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

    return ScriptMetadata(
        script_name=script_name,
        title=title,
        tags=tags,
        purpose=fields.get("purpose", ""),
        description=fields.get("description", ""),
        parameters=fields.get("parameters", ""),
        required_privileges=fields.get("required_privileges", ""),
        output_format=fields.get("output_format", ""),
        example_usage=fields.get("example_usage", ""),
        author=fields.get("author", ""),
    )


def parse_mysql_script(text: str) -> ParsedMySQLScript:
    """Parse a MySQL script into metadata and executable statements.

    Args:
        text (str): Raw SQL script text.

    Returns:
        ParsedMySQLScript: Parsed metadata and list of executable statements.
    """
    metadata = parse_header_metadata(text)
    statements = split_sql_statements(text)

    return ParsedMySQLScript(
        metadata=metadata,
        statements=statements,
    )


def split_sql_statements(text: str) -> list[str]:
    """Split SQL script text into individual executable statements.

    Respects single quotes, double quotes, backticks, line comments (-- and #),
    and block comments (/* */).

    Args:
        text (str): SQL script text.

    Returns:
        list[str]: Executable SQL statements with trailing semicolons stripped.
    """
    statements: list[str] = []
    buffer: list[str] = []
    i = 0
    length = len(text)
    in_single = False
    in_double = False
    in_backtick = False
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
            buffer.append(char)
            if char == "\\" and nxt:
                buffer.append(nxt)
                i += 2
                continue
            if char == "'":
                in_single = False
            i += 1
            continue

        if in_double:
            buffer.append(char)
            if char == "\\" and nxt:
                buffer.append(nxt)
                i += 2
                continue
            if char == '"':
                in_double = False
            i += 1
            continue

        if in_backtick:
            buffer.append(char)
            if char == "`":
                in_backtick = False
            i += 1
            continue

        if (char == "-" and nxt == "-") or char == "#":
            in_line_comment = True
            i += 2 if char == "-" else 1
            continue

        if char == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue

        if char == "'":
            in_single = True
            buffer.append(char)
            i += 1
            continue

        if char == '"':
            in_double = True
            buffer.append(char)
            i += 1
            continue

        if char == "`":
            in_backtick = True
            buffer.append(char)
            i += 1
            continue

        if char == ";":
            stmt = "".join(buffer).strip()
            if stmt:
                statements.append(stmt)
            buffer.clear()
            i += 1
            continue

        buffer.append(char)
        i += 1

    remaining = "".join(buffer).strip()
    if remaining:
        statements.append(remaining)

    return statements
