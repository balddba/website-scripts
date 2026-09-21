"""Integration test for oracle/sql/sql_baselines.sql."""

from __future__ import annotations

import oracledb
import pytest

from tests.oracle.conftest import RunOracleSql
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation


@pytest.mark.oracle
def test_sql_baselines(run_oracle_sql: RunOracleSql, oracle_settings: OracleTestSettings) -> None:
    """Execute sql_baselines.sql and verify plan baseline result columns.

    Args:
        run_oracle_sql (RunOracleSql): Fixture that executes a catalog script.
        oracle_settings (OracleTestSettings): Connection settings to ensure DB availability.
    """
    del oracle_settings
    try:
        result = run_oracle_sql("sql_baselines.sql", args=["%"])
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    assert result.queries, "sql_baselines.sql returned no query results"
    all_columns = {col.upper() for query in result.queries for col in query.columns}
    assert {"SQL_HANDLE", "PLAN_NAME", "ENABLED", "ACCEPTED", "FIXED"} <= all_columns
