"""Integration test for oracle/sql/sql_binds.sql."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import oracledb
import pytest

from tests.oracle.script_runner import oracle_connection, run_script
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation


@pytest.mark.oracle
def test_sql_binds(oracle_settings: OracleTestSettings) -> None:
    """Execute a parameterized query and verify sql_binds.sql reports bind metadata.

    Args:
        oracle_settings (OracleTestSettings): Validated connection settings.
    """
    with seeded_bind_statement(oracle_settings) as connection:
        try:
            result = run_script(connection, "sql_binds.sql", args=["%"])
        except oracledb.DatabaseError as exc:
            if _is_environment_limitation(exc):
                pytest.skip(str(exc).split("\n", maxsplit=1)[0])
            raise

    assert result.queries, "sql_binds.sql returned no query results"
    all_columns = {col.upper() for query in result.queries for col in query.columns}
    assert "NAME" in all_columns or "POSITION" in all_columns
    assert "DATATYPE_STRING" in all_columns or "VALUE_STRING" in all_columns


@contextmanager
def seeded_bind_statement(oracle_settings: OracleTestSettings) -> Iterator[oracledb.Connection]:
    """Execute a statement with a bind variable in an open Oracle connection.

    Args:
        oracle_settings (OracleTestSettings): Validated connection settings.

    Yields:
        oracledb.Connection: Open connection that executed the bind statement.
    """
    with oracle_connection(oracle_settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT /* WS_BINDS_SEED */ :ws_test_bind_val FROM dual",
                {"ws_test_bind_val": "HELLO_BIND"},
            )
            cursor.fetchall()
        yield connection
