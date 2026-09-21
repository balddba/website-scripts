"""Offline unit tests for the SQL*Plus catalog preprocessor."""

from __future__ import annotations

from tests.oracle.script_parser import apply_substitutions, parse_sqlplus_script
from tests.oracle.script_runner import SQL_DIR

WHOAMI = """\
/*******************************************************************************
*
* Script Name: whoami.sql
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
COLUMN name FORMAT A22 HEADING 'Name'

PROMPT === Who am I ===

SELECT USER AS name FROM dual;

COLUMN name CLEAR
SET FEEDBACK ON
"""

COMPILE = """\
SET SERVEROUTPUT ON SIZE UNLIMITED
COLUMN c_target NEW_VALUE p_target NOPRINT
SELECT NVL(NULLIF(TRIM('&1'), ''), '%') AS c_target FROM dual;

DECLARE
    v_raw VARCHAR2(257) := TRIM('&&p_target');
BEGIN
    NULL;
END;
/
"""

LAST_SQL = """\
COLUMN c_sid NEW_VALUE p_sid NOPRINT
SELECT NVL(NULLIF(TRIM('&1'), ''), SYS_CONTEXT('USERENV', 'SID')) AS c_sid
FROM dual;

VARIABLE filter_sid NUMBER

BEGIN
    :filter_sid := TO_NUMBER('&&p_sid');
END;
/

SELECT s.sid
FROM v$session s
WHERE s.sid = :filter_sid;
"""


def test_whoami_strips_set_prompt_and_column() -> None:
    """Keep the SELECT from a formatted report script."""
    parsed = parse_sqlplus_script(WHOAMI)
    assert len(parsed.statements) == 1
    sql = parsed.statements[0].upper()
    assert "SELECT" in sql
    assert "PROMPT" not in sql
    assert "SET VERIFY" not in sql
    assert "COLUMN" not in sql


def test_strips_abbreviated_column_command() -> None:
    """Treat SQL*Plus COL as COLUMN, not executable SQL."""
    parsed = parse_sqlplus_script(
        """
        COL plan_table_output FORMAT A150
        SELECT * FROM TABLE(xplan.display);
        """
    )
    assert len(parsed.statements) == 1
    assert parsed.statements[0].startswith("SELECT")


def test_create_type_sql_ddl_drops_trailing_semicolon() -> None:
    """Simple object type DDL executes through drivers without SQL*Plus terminators."""
    parsed = parse_sqlplus_script(
        """
        CREATE OR REPLACE TYPE xplan_ot AS OBJECT
        ( plan_table_output VARCHAR2(300) );
        /
        """
    )
    assert parsed.statements == ["CREATE OR REPLACE TYPE xplan_ot AS OBJECT\n        ( plan_table_output VARCHAR2(300) )"]


def test_compile_captures_new_value_and_plsql_slash() -> None:
    """Split the NEW_VALUE query from the slash-terminated PL/SQL block."""
    parsed = parse_sqlplus_script(COMPILE)
    assert parsed.new_values == {"C_TARGET": "p_target"}
    assert len(parsed.statements) == 2
    assert "FROM dual" in parsed.statements[0]
    assert parsed.statements[1].strip().startswith("DECLARE")
    assert parsed.statements[1].strip().endswith("END;")


def test_last_sql_captures_variable_and_bind() -> None:
    """Record VARIABLE declarations and keep `:filter_sid` in later SQL."""
    parsed = parse_sqlplus_script(LAST_SQL)
    assert parsed.variables == {"FILTER_SID": "NUMBER"}
    assert parsed.new_values == {"C_SID": "p_sid"}
    assert len(parsed.statements) == 3
    assert ":filter_sid" in parsed.statements[1]
    assert ":filter_sid" in parsed.statements[2]


def test_positional_substitution_replaces_ampersand_one() -> None:
    """Replace `&1` with the first argument."""
    sql = "SELECT NVL(NULLIF(TRIM('&1'), ''), '%') AS c_target FROM dual"
    assert apply_substitutions(sql, ["HR"], {}) == "SELECT NVL(NULLIF(TRIM('HR'), ''), '%') AS c_target FROM dual"


def test_named_substitution_uses_new_value_define() -> None:
    """Replace `&&p_target` from the define map."""
    sql = "v_raw VARCHAR2(257) := TRIM('&&p_target');"
    assert apply_substitutions(sql, [], {"P_TARGET": "HR"}) == "v_raw VARCHAR2(257) := TRIM('HR');"


def test_missing_positional_becomes_empty_string() -> None:
    """Leave optional `&1` empty when no argument is passed."""
    sql = "TRIM('&1')"
    assert apply_substitutions(sql, [], {}) == "TRIM('')"


def test_define_awr_markers_from_xplan_package() -> None:
    """Capture DEFINE `_awr_start` used to comment out AWR code."""
    parsed = parse_sqlplus_script(
        """
        DEFINE _awr_start = "/*"
        DEFINE _awr_end   = "*/"
        BEGIN
        &_awr_start
            NULL;
        &_awr_end
        END;
        /
        """
    )
    assert parsed.defines["_AWR_START"] == "/*"
    assert parsed.defines["_AWR_END"] == "*/"
    combined = apply_substitutions(parsed.statements[0], [], parsed.defines)
    assert "/*" in combined
    assert "*/" in combined


def test_parses_real_whoami_catalog_file() -> None:
    """Parse oracle/sql/whoami.sql without a database."""
    parsed = parse_sqlplus_script((SQL_DIR / "whoami.sql").read_text())
    assert parsed.statements
    assert any("v$session" in stmt.lower() for stmt in parsed.statements)


def test_parses_real_compile_catalog_file() -> None:
    """Parse oracle/sql/compile.sql into a bind query plus a PL/SQL block."""
    parsed = parse_sqlplus_script((SQL_DIR / "compile.sql").read_text())
    assert "C_TARGET" in parsed.new_values
    assert any(stmt.strip().upper().startswith("DECLARE") for stmt in parsed.statements)
    assert any("FROM dual" in stmt for stmt in parsed.statements)


def test_parses_real_last_sql_catalog_file() -> None:
    """Parse oracle/sql/last_sql.sql VARIABLE and slash-terminated assignment."""
    parsed = parse_sqlplus_script((SQL_DIR / "last_sql.sql").read_text())
    assert parsed.variables["FILTER_SID"].upper().startswith("NUMBER")
    assert any(":filter_sid" in stmt for stmt in parsed.statements)
