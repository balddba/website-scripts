"""Integration test for oracle/sql/recyclebin_summary.sql."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import oracledb
import pytest

from tests.oracle.script_runner import ScriptResult, oracle_connection, quote_ident
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation

RECYCLE_TABLE = "WS_SQLTEST_RECYCLE_TAB"


@pytest.mark.oracle
def test_recyclebin_summary_reports_dropped_objects(run_oracle_sql, oracle_settings) -> None:
    """Drop a table into the recyclebin, verify recyclebin_summary.sql reports it, and clean up."""
    with seeded_recyclebin_objects(oracle_settings) as schema:
        try:
            result = run_oracle_sql("recyclebin_summary.sql")
        except oracledb.DatabaseError as exc:
            if _is_environment_limitation(exc):
                pytest.skip(str(exc).split("\n", maxsplit=1)[0])
            raise

    assert _has_value(result, "OWNER", schema)
    assert _has_recyclebin_summary(result, schema)


@contextmanager
def seeded_recyclebin_objects(oracle_settings: OracleTestSettings) -> Iterator[str]:
    """Create and drop a table without PURGE to populate the recyclebin.

    Args:
        oracle_settings (OracleTestSettings): Validated connection settings.

    Yields:
        str: Schema name owning the recyclebin objects.
    """
    schema = quote_ident(oracle_settings.schema_name)
    target = f"{schema}.{RECYCLE_TABLE}"
    try:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_table(cursor, target)
            _purge_recyclebin(cursor)
            cursor.execute(
                f"""
                CREATE TABLE {target} (
                    id NUMBER PRIMARY KEY,
                    payload VARCHAR2(64) NOT NULL
                )
                """
            )
            cursor.execute(
                f"""
                INSERT INTO {target} (id, payload)
                SELECT LEVEL, 'recycle-' || LEVEL
                FROM dual
                CONNECT BY LEVEL <= 5
                """
            )
            connection.commit()
            cursor.execute(f"DROP TABLE {target}")
            cursor.execute(
                "SELECT COUNT(*) FROM user_recyclebin WHERE original_name = :name",
                {"name": RECYCLE_TABLE},
            )
            retained = int(cursor.fetchone()[0])
            if retained == 0:
                pytest.skip("The test database did not retain the table in the recycle bin")
        yield schema
    finally:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _purge_recyclebin(cursor)
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


def _purge_recyclebin(cursor: oracledb.Cursor) -> None:
    """Purge the recyclebin to clean up test artifacts.

    Args:
        cursor (oracledb.Cursor): Active database cursor.
    """
    try:
        cursor.execute("PURGE RECYCLEBIN")
    except oracledb.DatabaseError as exc:
        message = str(exc)
        if not any(code in message for code in ("ORA-00942", "ORA-38302", "ORA-01031")):
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


def _has_recyclebin_summary(result: ScriptResult, owner: str) -> bool:
    """Return True when recyclebin output contains positive counts and space for the owner.

    Args:
        result (ScriptResult): Script execution result.
        owner (str): Expected schema owner.

    Returns:
        bool: True if a matching summary row is found.
    """
    for query in result.queries:
        try:
            owner_idx = query.column_index("OWNER")
            obj_cnt_idx = query.column_index("OBJECT_COUNT")
            tab_cnt_idx = query.column_index("TABLE_COUNT")
            space_mb_idx = query.column_index("SPACE_MB")
        except KeyError:
            continue
        for row in query.rows:
            if row[owner_idx] == owner and row[obj_cnt_idx] is not None and int(row[obj_cnt_idx]) >= 1 and row[tab_cnt_idx] is not None and int(row[tab_cnt_idx]) >= 1 and row[space_mb_idx] is not None and float(row[space_mb_idx]) >= 0:
                return True
    return False
