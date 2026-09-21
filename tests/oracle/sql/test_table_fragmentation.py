"""Integration test for oracle/sql/table_fragmentation.sql."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import oracledb
import pytest

from tests.oracle.script_runner import ScriptResult, oracle_connection, quote_ident
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation

FRAG_TABLE = "WS_SQLTEST_FRAG_TAB"


@pytest.mark.oracle
def test_table_fragmentation_reports_slack(run_oracle_sql, oracle_settings) -> None:
    """Seed table with deleted rows and stale stats, verify table_fragmentation.sql, and clean up."""
    with seeded_fragmented_table(oracle_settings) as schema:
        try:
            result = run_oracle_sql("table_fragmentation.sql", args=[schema])
        except oracledb.DatabaseError as exc:
            if _is_environment_limitation(exc):
                pytest.skip(str(exc).split("\n", maxsplit=1)[0])
            raise

    assert _has_value(result, "OWNER", schema)
    assert _has_value(result, "TABLE_NAME", FRAG_TABLE)
    assert _has_row(result, {"OWNER": schema, "TABLE_NAME": FRAG_TABLE})
    assert _has_valid_fragmentation_metrics(result, schema, FRAG_TABLE)


@contextmanager
def seeded_fragmented_table(oracle_settings: OracleTestSettings) -> Iterator[str]:
    """Create a table with high-water-mark slack by inserting, gathering stats, and deleting rows.

    Args:
        oracle_settings (OracleTestSettings): Validated connection settings.

    Yields:
        str: Schema name owning the fragmented table.
    """
    schema = quote_ident(oracle_settings.schema_name)
    target = f"{schema}.{FRAG_TABLE}"
    with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
        _drop_table(cursor, target)
        cursor.execute(
            f"""
            CREATE TABLE {target} (
                id NUMBER PRIMARY KEY,
                payload VARCHAR2(200) NOT NULL
            )
            """
        )
        cursor.execute(
            f"""
            INSERT INTO {target} (id, payload)
            SELECT LEVEL, RPAD('frag-data-', 180, 'x')
            FROM dual
            CONNECT BY LEVEL <= 500
            """
        )
        connection.commit()
        cursor.callproc("dbms_stats.gather_table_stats", [schema, FRAG_TABLE])
        cursor.execute(f"DELETE FROM {target} WHERE id > 50")
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


def _has_valid_fragmentation_metrics(result: ScriptResult, owner: str, table_name: str) -> bool:
    """Return True when the table fragmentation row contains non-null metrics.

    Args:
        result (ScriptResult): Script execution result.
        owner (str): Expected schema owner.
        table_name (str): Expected table name.

    Returns:
        bool: True if matching row has populated numeric/date metrics.
    """
    for query in result.queries:
        try:
            owner_idx = query.column_index("OWNER")
            tab_idx = query.column_index("TABLE_NAME")
            num_rows_idx = query.column_index("NUM_ROWS")
            alloc_mb_idx = query.column_index("ALLOCATED_MB")
            wasted_mb_idx = query.column_index("WASTED_MB")
            last_analyzed_idx = query.column_index("LAST_ANALYZED")
        except KeyError:
            continue
        for row in query.rows:
            if row[owner_idx] == owner and row[tab_idx] == table_name and row[num_rows_idx] is not None and row[alloc_mb_idx] is not None and row[wasted_mb_idx] is not None and row[last_analyzed_idx] is not None:
                return True
    return False
