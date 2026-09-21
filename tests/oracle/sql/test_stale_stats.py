"""Integration test for oracle/sql/stale_stats.sql."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import oracledb
import pytest

from tests.oracle.script_runner import ScriptResult, oracle_connection, quote_ident
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation

STALE_TABLE = "WS_SQLTEST_STALE_TAB"


@pytest.mark.oracle
def test_stale_stats_reports_stale_table(run_oracle_sql, oracle_settings: OracleTestSettings) -> None:
    """Create a table, gather stats, mutate data to trigger staleness, and verify report."""
    with seeded_stale_table(oracle_settings) as schema:
        try:
            result = run_oracle_sql("stale_stats.sql", args=[schema])
        except oracledb.DatabaseError as exc:
            if _is_environment_limitation(exc):
                pytest.skip(str(exc).split("\n", maxsplit=1)[0])
            raise

    assert _has_value(result, "TABLE_NAME", STALE_TABLE)
    assert _has_row(result, {"OWNER": schema, "TABLE_NAME": STALE_TABLE, "STALE_STATS": "YES"})


@contextmanager
def seeded_stale_table(oracle_settings: OracleTestSettings) -> Iterator[str]:
    """Create and seed a table, gather stats, and insert rows to trigger staleness.

    Args:
        oracle_settings (OracleTestSettings): Validated connection settings.

    Yields:
        str: Validated upper-case schema name.
    """
    schema = quote_ident(oracle_settings.schema_name)
    target = f"{schema}.{STALE_TABLE}"
    try:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_table(cursor, target)
            cursor.execute(
                f"""
                CREATE TABLE {target} (
                    id NUMBER PRIMARY KEY,
                    payload VARCHAR2(64) NOT NULL
                )
                """
            )
            cursor.executemany(
                f"INSERT INTO {target} (id, payload) VALUES (:1, :2)",
                [(i, f"stale-row-{i}") for i in range(1, 11)],
            )
            connection.commit()
            cursor.callproc("DBMS_STATS.GATHER_TABLE_STATS", [schema, STALE_TABLE])
            cursor.executemany(
                f"INSERT INTO {target} (id, payload) VALUES (:1, :2)",
                [(i, f"stale-extra-{i}") for i in range(11, 25)],
            )
            connection.commit()
            try:
                cursor.callproc("DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO")
            except oracledb.DatabaseError as exc:
                if _is_environment_limitation(exc):
                    pytest.skip(str(exc).split("\n", maxsplit=1)[0])
                raise
        yield schema
    finally:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_table(cursor, target)


def _drop_table(cursor: oracledb.Cursor, target: str) -> None:
    """Drop a test table if it exists.

    Args:
        cursor (oracledb.Cursor): Database cursor.
        target (str): Qualified or unqualified table name.
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
        expected (object): Value to match.

    Returns:
        bool: True if expected is found in column values.
    """
    for query in result.queries:
        try:
            values = query.values(column)
        except KeyError:
            continue
        if expected in values:
            return True
    return False


def _has_row(
    result: ScriptResult,
    expected: dict[str, object],
    *,
    required: set[str] | None = None,
) -> bool:
    """Return True when a result row has expected values and columns.

    Args:
        result (ScriptResult): Script execution result.
        expected (dict[str, object]): Column name to expected value mapping.
        required (set[str] | None): Optional extra column names that must exist.

    Returns:
        bool: True if any row matches all expected values.
    """
    columns = set(expected) | (required or set())
    for query in result.queries:
        available = {col.upper() for col in query.columns}
        if not (columns <= available):
            continue
        indexes = {column: query.column_index(column) for column in expected}
        if any(all(row[indexes[col]] == val for col, val in expected.items()) for row in query.rows):
            return True
    return False
