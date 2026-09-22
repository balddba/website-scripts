"""Unit tests for the MySQL catalog script parser and metadata validator."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.mysql.script_parser import parse_header_metadata, parse_mysql_script, split_sql_statements

REPO_ROOT = Path(__file__).resolve().parents[2]
MYSQL_SQL_DIR = REPO_ROOT / "mysql" / "sql"

SAMPLE_SCRIPT = """\
/*******************************************************************************
*
* Script Name: test_sample.sql
* Title: Sample test script
* Tags: Performance, Testing
* Purpose: Reports sample metrics for unit testing
*
* Description:
*   Multi-line description of the sample script.
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT
*
* Output Format:
*   - col1: Column one
*   - col2: Column two
*
* Example Usage:
*   mysql < test_sample.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT 'hello; world' AS col1, 123 AS col2;
"""


def test_parse_header_metadata_extracts_all_fields() -> None:
    """Validate extraction of title, tags, purpose, and author from header."""
    metadata = parse_header_metadata(SAMPLE_SCRIPT)
    assert metadata is not None
    assert metadata.script_name == "test_sample.sql"
    assert metadata.title == "Sample test script"
    assert metadata.tags == ["Performance", "Testing"]
    assert metadata.purpose == "Reports sample metrics for unit testing"
    assert metadata.author == "Aaron Myers <aaron@balddba.com>"
    assert "Multi-line description" in metadata.description
    assert metadata.parameters == "None"
    assert metadata.required_privileges == "- SELECT"


def test_split_sql_statements_handles_semicolons_in_strings_and_comments() -> None:
    """Verify statement splitter does not break on semicolons inside string literals or comments."""
    sql = """
    -- Comment with a semicolon ; inside
    /* Block comment with ; inside */
    SELECT 'foo;bar' AS val, "test;case" AS val2;
    SELECT `col;name` FROM my_table WHERE id = 1;
    """
    statements = split_sql_statements(sql)
    assert len(statements) == 2
    assert "foo;bar" in statements[0]
    assert "my_table" in statements[1]


def test_split_sql_statements_handles_escaped_quotes() -> None:
    """Verify statement splitter respects escaped quotes in string literals."""
    sql = r"SELECT 'it\'s a test;' AS greeting; SELECT 'second' AS msg;"
    statements = split_sql_statements(sql)
    assert len(statements) == 2
    assert r"it\'s a test;" in statements[0]
    assert "second" in statements[1]


def test_all_catalog_sql_files_exist_and_are_discoverable() -> None:
    """Ensure mysql/sql contains catalog scripts."""
    sql_files = list(MYSQL_SQL_DIR.glob("*.sql"))
    assert len(sql_files) >= 12


def test_every_mysql_script_has_an_integration_test() -> None:
    """Require a matching per-script test module for every catalog SQL file."""
    test_dir = Path(__file__).parent / "sql"
    scripts = {path.stem for path in MYSQL_SQL_DIR.glob("*.sql")}
    tested_scripts = {path.stem.removeprefix("test_") for path in test_dir.glob("test_*.py")}

    assert tested_scripts == scripts


@pytest.mark.parametrize(
    "sql_file",
    sorted(MYSQL_SQL_DIR.glob("*.sql")),
    ids=lambda path: path.name,
)
def test_catalog_sql_files_have_valid_metadata_headers(sql_file: Path) -> None:
    """Verify every SQL file under mysql/sql has a complete header matching guidelines."""
    text = sql_file.read_text()
    parsed = parse_mysql_script(text)

    assert parsed.metadata is not None, f"Missing boxed comment header in {sql_file.name}"
    assert parsed.metadata.script_name == sql_file.name, f"Script Name in header ({parsed.metadata.script_name}) does not match filename ({sql_file.name})"
    assert len(parsed.metadata.title) > 0, f"Missing Title in {sql_file.name}"
    assert len(parsed.metadata.tags) > 0, f"Missing Tags in {sql_file.name}"
    assert len(parsed.metadata.purpose) > 0, f"Missing Purpose in {sql_file.name}"
    assert "Aaron Myers <aaron@balddba.com>" in parsed.metadata.author, f"Missing or invalid Author in {sql_file.name}"
    assert len(parsed.statements) >= 1, f"No executable SQL statements found in {sql_file.name}"
