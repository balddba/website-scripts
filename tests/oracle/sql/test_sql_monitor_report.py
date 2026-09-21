"""Integration test for oracle/sql/sql_monitor_report.sql."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import oracledb
import pytest

from tests.oracle.script_runner import oracle_connection, run_script
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation


@pytest.mark.oracle
def test_sql_monitor_report(oracle_settings: OracleTestSettings) -> None:
    """Execute a monitored statement and verify sql_monitor_report.sql output columns.

    Args:
        oracle_settings (OracleTestSettings): Validated connection settings.
    """
    with seeded_monitored_query(oracle_settings) as connection:
        try:
            result = run_script(connection, "sql_monitor_report.sql", args=["%"])
        except oracledb.DatabaseError as exc:
            if _is_environment_limitation(exc):
                pytest.skip(str(exc).split("\n", maxsplit=1)[0])
            raise

    assert result.queries, "sql_monitor_report.sql returned no query results"
    all_columns = {col.upper() for query in result.queries for col in query.columns}
    assert "SQL_ID" in all_columns or "KEY" in all_columns
    assert "STATUS" in all_columns
    assert "USERNAME" in all_columns
    assert bool(all_columns & {"ELAPSED_SEC", "CPU_SEC", "ELAPSED_TIME_SEC", "CPU_TIME_SEC"})


@contextmanager
def seeded_monitored_query(oracle_settings: OracleTestSettings) -> Iterator[oracledb.Connection]:
    """Execute a query with a MONITOR hint in an open Oracle connection.

    Args:
        oracle_settings (OracleTestSettings): Validated connection settings.

    Yields:
        oracledb.Connection: Open connection that executed the monitored query.
    """
    with oracle_connection(oracle_settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT /*+ MONITOR WS_MONITOR_SEED */ count(*) FROM dual")
            cursor.fetchall()
        yield connection
