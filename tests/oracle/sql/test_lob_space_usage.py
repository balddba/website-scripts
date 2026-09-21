"""Integration test for oracle/sql/lob_space_usage.sql."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import oracledb
import pytest

from tests.oracle.script_runner import ScriptResult, oracle_connection, quote_ident
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation

LOB_TABLE = "WS_SQLTEST_LOB_TAB"


@pytest.mark.oracle
def test_lob_space_usage_reports_seeded_lob(run_oracle_sql, oracle_settings) -> None:
    """Create a table with a CLOB column, verify lob_space_usage.sql reports it, and clean up."""
    with seeded_lob_objects(oracle_settings) as schema:
        try:
            result = run_oracle_sql("lob_space_usage.sql", args=[schema])
        except oracledb.DatabaseError as exc:
            if _is_environment_limitation(exc):
                pytest.skip(str(exc).split("\n", maxsplit=1)[0])
            raise

    assert _has_value(result, "OWNER", schema)
    assert _has_value(result, "TABLE_NAME", LOB_TABLE)
    assert _has_value(result, "COLUMN_NAME", "PAYLOAD")
    assert _has_row(
        result,
        {
            "OWNER": schema,
            "TABLE_NAME": LOB_TABLE,
            "COLUMN_NAME": "PAYLOAD",
        },
    )


@contextmanager
def seeded_lob_objects(oracle_settings: OracleTestSettings) -> Iterator[str]:
    """Create a table with a CLOB column for lob_space_usage.sql.

    Args:
        oracle_settings (OracleTestSettings): Validated connection settings.

    Yields:
        str: Schema name owning the LOB table.
    """
    schema = quote_ident(oracle_settings.schema_name)
    target = f"{schema}.{LOB_TABLE}"
    with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
        _drop_table(cursor, target)
        cursor.execute(
            f"""
            CREATE TABLE {target} (
                id NUMBER PRIMARY KEY,
                payload CLOB
            )
            """
        )
        cursor.execute(
            f"""
            INSERT INTO {target} (id, payload)
            VALUES (1, TO_CLOB('lob-test-payload-') || RPAD('x', 4000, 'x'))
            """
        )
        connection.commit()
    try:
        yield schema
    finally:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_table(cursor, target)
            connection.commit()


def _drop_table(cursor: oracledb.Cursor, target: str) -> None:
    """Drop a fixture table if it exists.

    Args:
        cursor (oracledb.Cursor): Active database cursor.
        target (str): Qualified table name to drop.
    """
    try:
        cursor.execute(f"DROP TABLE {target} PURGE")
    except oracledb.DatabaseError as exc:
        if "ORA-00942" not in str(exc):
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


def _has_row(result: ScriptResult, expected: dict[str, object]) -> bool:
    """Return True when any result set includes all expected column values.

    Args:
        result (ScriptResult): Script execution result.
        expected (dict[str, object]): Column-to-value mapping to match.

    Returns:
        bool: True if a matching row is found in any result set.
    """
    for query in result.queries:
        indexes = {}
        for column in expected:
            try:
                indexes[column] = query.column_index(column)
            except KeyError:
                indexes = {}
                break
        if not indexes:
            continue
        for row in query.rows:
            if all(row[index] == value for column, value in expected.items() for index in [indexes[column]]):
                return True
    return False
