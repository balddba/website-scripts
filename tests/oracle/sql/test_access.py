"""Integration test for oracle/sql/access.sql."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import oracledb
import pytest

from tests.oracle.script_runner import ScriptResult, oracle_connection, quote_ident
from tests.oracle.sql.harness import _is_environment_limitation

ACCESS_TABLE = "WS_SQLTEST_ACCESS"


@pytest.mark.oracle
def test_access_reports_seeded_object_grants(run_oracle_sql, oracle_settings) -> None:
    """Create grants for access.sql, verify report rows, and clean up."""
    with seeded_access_object(oracle_settings) as target:
        try:
            result = run_oracle_sql("access.sql", args=[target, "PUBLIC"])
        except oracledb.DatabaseError as exc:
            if _is_environment_limitation(exc):
                pytest.skip(str(exc).split("\n", maxsplit=1)[0])
            raise

    assert _has_value(result, "OWNER", oracle_settings.schema_name.upper())
    assert _has_value(result, "OBJECT_NAME", ACCESS_TABLE)
    assert _has_row(result, {"GRANTEE": "PUBLIC", "PRIVILEGE": "SELECT", "COLUMN_NAME": None})
    assert _has_row(result, {"GRANTEE": "PUBLIC", "PRIVILEGE": "UPDATE", "COLUMN_NAME": "PAYLOAD"})


@contextmanager
def seeded_access_object(oracle_settings) -> Iterator[str]:
    """Create a table and grants that access.sql should report."""
    schema = quote_ident(oracle_settings.schema_name)
    target = f"{schema}.{ACCESS_TABLE}"
    with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
        _drop_access_table(cursor, schema)
        cursor.execute(
            f"""
                CREATE TABLE {schema}.{ACCESS_TABLE} (
                    id NUMBER PRIMARY KEY,
                    payload VARCHAR2(64) NOT NULL
                )
                """
        )
        cursor.execute(
            f"""
                INSERT INTO {schema}.{ACCESS_TABLE} (id, payload)
                SELECT LEVEL, 'access-row-' || LEVEL
                FROM dual
                CONNECT BY LEVEL <= 3
                """
        )
        cursor.execute(f"GRANT SELECT ON {schema}.{ACCESS_TABLE} TO PUBLIC")
        cursor.execute(f"GRANT UPDATE (payload) ON {schema}.{ACCESS_TABLE} TO PUBLIC")
        connection.commit()
    try:
        yield target
    finally:
        with oracle_connection(oracle_settings) as connection:
            with connection.cursor() as cursor:
                _drop_access_table(cursor, schema)
            connection.commit()


def _drop_access_table(cursor: oracledb.Cursor, schema: str) -> None:
    """Drop the access test table when a previous test left it behind."""
    try:
        cursor.execute(f"DROP TABLE {schema}.{ACCESS_TABLE} PURGE")
    except oracledb.DatabaseError as exc:
        if "ORA-00942" not in str(exc):
            raise


def _has_value(result: ScriptResult, column: str, expected: object) -> bool:
    """Return True when any result set includes a column value."""
    for query in result.queries:
        try:
            values = query.values(column)
        except KeyError:
            continue
        if expected in values:
            return True
    return False


def _has_row(result: ScriptResult, expected: dict[str, object]) -> bool:
    """Return True when any result set includes all expected column values."""
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
