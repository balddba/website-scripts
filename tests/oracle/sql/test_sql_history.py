"""Integration test for oracle/sql/sql_history.sql."""

from __future__ import annotations

import oracledb
import pytest

from tests.oracle.conftest import RunOracleSql
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation


@pytest.mark.oracle
def test_sql_history(run_oracle_sql: RunOracleSql, oracle_settings: OracleTestSettings) -> None:
    """Execute sql_history.sql with a wildcard pattern and verify result columns.

    Args:
        run_oracle_sql (RunOracleSql): Fixture that executes a catalog script.
        oracle_settings (OracleTestSettings): Connection settings to ensure DB availability.
    """
    del oracle_settings
    try:
        result = run_oracle_sql("sql_history.sql", args=["%"])
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    assert result.queries, "sql_history.sql returned no query results"
    all_columns = {col.upper() for query in result.queries for col in query.columns}
    assert "SQL_ID" in all_columns
    assert "PLAN_HASH_VALUE" in all_columns
    assert "EXECUTIONS" in all_columns
    assert bool(all_columns & {"ELAPSED_SEC", "ELA_PER_EXEC", "ELAPSED_TIME_MS", "ELAPSED_TIME"})
    assert bool(all_columns & {"GETS_PER_EXEC", "BUFFER_GETS", "BUFFER_GETS_DELTA"})
