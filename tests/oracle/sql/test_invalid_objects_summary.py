"""Integration test for oracle/sql/invalid_objects_summary.sql."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import oracledb
import pytest

from tests.oracle.script_runner import ScriptResult, oracle_connection, quote_ident
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation

INVALID_VIEW = "WS_SQLTEST_INV_VIEW"


@pytest.mark.oracle
def test_invalid_objects_summary_reports_invalid_view(run_oracle_sql, oracle_settings) -> None:
    """Create an invalid view, verify invalid_objects_summary.sql reports it, and clean up."""
    with seeded_invalid_objects(oracle_settings) as schema:
        try:
            result = run_oracle_sql("invalid_objects_summary.sql")
        except oracledb.DatabaseError as exc:
            if _is_environment_limitation(exc):
                pytest.skip(str(exc).split("\n", maxsplit=1)[0])
            raise

    assert _has_value(result, "OWNER", schema)
    assert _has_value(result, "OBJECT_TYPE", "VIEW")
    assert _has_invalid_entry(result, schema, "VIEW")


@contextmanager
def seeded_invalid_objects(oracle_settings: OracleTestSettings) -> Iterator[str]:
    """Create an invalid view that invalid_objects_summary.sql should report.

    Args:
        oracle_settings (OracleTestSettings): Validated connection settings.

    Yields:
        str: Schema name owning the invalid view.
    """
    schema = quote_ident(oracle_settings.schema_name)
    target = f"{schema}.{INVALID_VIEW}"
    with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
        _drop_invalid_view(cursor, target)
        try:
            cursor.execute(f"CREATE OR REPLACE FORCE VIEW {target} AS SELECT * FROM {schema}.NON_EXISTENT_TABLE_XYZ")
        except oracledb.DatabaseError as exc:
            if "ORA-24344" not in str(exc):
                raise
        connection.commit()
    try:
        yield schema
    finally:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_invalid_view(cursor, target)
            connection.commit()


def _drop_invalid_view(cursor: oracledb.Cursor, target: str) -> None:
    """Drop the invalid test view if it exists.

    Args:
        cursor (oracledb.Cursor): Active database cursor.
        target (str): Qualified view name to drop.
    """
    try:
        cursor.execute(f"DROP VIEW {target}")
    except oracledb.DatabaseError as exc:
        message = str(exc)
        if not any(code in message for code in ("ORA-00942", "ORA-04043")):
            raise


def _has_value(result: ScriptResult, column: str, expected: object) -> bool:
    """Return True when any result set includes a column value.

    Args:
        result (ScriptResult): Script execution result.
        column (str): Column name to inspect.
        expected (object): Value expected in the column.

    Returns:
        bool: True if the value appears in the result column.
    """
    for query in result.queries:
        try:
            values = query.values(column)
        except KeyError:
            continue
        if expected in values:
            return True
    return False


def _has_invalid_entry(result: ScriptResult, owner: str, object_type: str) -> bool:
    """Return True when a result row has matching owner, object type, and invalid count >= 1.

    Args:
        result (ScriptResult): Script execution result.
        owner (str): Expected object owner.
        object_type (str): Expected object type.

    Returns:
        bool: True if an invalid object entry is found with count >= 1.
    """
    for query in result.queries:
        try:
            owner_idx = query.column_index("OWNER")
            type_idx = query.column_index("OBJECT_TYPE")
            count_idx = query.column_index("INVALID_COUNT")
        except KeyError:
            continue
        for row in query.rows:
            if row[owner_idx] == owner and row[type_idx] == object_type and row[count_idx] is not None and int(row[count_idx]) >= 1:
                return True
    return False
