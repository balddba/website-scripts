"""Integration test for oracle/sql/sql_patches_profiles.sql."""

from __future__ import annotations

import oracledb
import pytest

from tests.oracle.conftest import RunOracleSql
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation


@pytest.mark.oracle
def test_sql_patches_profiles(run_oracle_sql: RunOracleSql, oracle_settings: OracleTestSettings) -> None:
    """Execute sql_patches_profiles.sql and verify SQL profile and patch columns.

    Args:
        run_oracle_sql (RunOracleSql): Fixture that executes a catalog script.
        oracle_settings (OracleTestSettings): Connection settings to ensure DB availability.
    """
    del oracle_settings
    try:
        result = run_oracle_sql("sql_patches_profiles.sql", args=["%"])
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    assert result.queries, "sql_patches_profiles.sql returned no query results"
    all_columns = {col.upper() for query in result.queries for col in query.columns}
    assert {"NAME", "CATEGORY", "STATUS"} <= all_columns
    assert "TYPE" in all_columns
    assert "CREATED" in all_columns or "CREATED_TIME" in all_columns
