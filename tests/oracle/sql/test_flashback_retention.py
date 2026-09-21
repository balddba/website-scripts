"""Integration test for oracle/sql/flashback_retention.sql."""

from __future__ import annotations

import oracledb
import pytest

from tests.oracle.script_runner import QueryResult, ScriptResult
from tests.oracle.sql.harness import _is_environment_limitation

EXPECTED_FLASHBACK_CONFIG_COLUMNS = {"FLASHBACK_ON"}
EXPECTED_FLASHBACK_LOG_COLUMNS = {
    "OLDEST_TIME",
    "TARGET_MIN",
    "EST_SIZE_MB",
}


@pytest.mark.oracle
def test_flashback_retention(run_oracle_sql) -> None:
    """Execute flashback_retention.sql and verify flashback retention columns.

    Args:
        run_oracle_sql: Fixture to execute a SQL script.
    """
    try:
        result = run_oracle_sql("flashback_retention.sql")
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    config_query = _query_with_columns(result, EXPECTED_FLASHBACK_CONFIG_COLUMNS)
    assert config_query is not None, "flashback_retention.sql did not return database configuration with FLASHBACK_ON"

    log_query = _query_with_columns(result, EXPECTED_FLASHBACK_LOG_COLUMNS)
    assert log_query is not None, f"flashback_retention.sql did not return flashback log query with columns {sorted(EXPECTED_FLASHBACK_LOG_COLUMNS)}"


def _query_with_columns(result: ScriptResult, columns: set[str]) -> QueryResult | None:
    """Return the first result set containing all requested columns.

    Args:
        result (ScriptResult): Script execution result.
        columns (set[str]): Upper-case column names that must be present.

    Returns:
        QueryResult | None: Matching query result set if found, else None.
    """
    for query in result.queries:
        if columns <= {col.upper() for col in query.columns}:
            return query
    return None
