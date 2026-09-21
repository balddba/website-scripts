"""Integration test for oracle/sql/dg_apply_lag.sql."""

from __future__ import annotations

import oracledb
import pytest

from tests.oracle.script_runner import QueryResult, ScriptResult
from tests.oracle.sql.harness import _is_environment_limitation

EXPECTED_LAG_COLUMNS = {"METRIC_NAME", "METRIC_VALUE"}
EXPECTED_PROCESS_COLUMNS = {"PROCESS_NAME", "STATUS"}


@pytest.mark.oracle
def test_dg_apply_lag(run_oracle_sql) -> None:
    """Execute dg_apply_lag.sql and verify Data Guard lag and process columns.

    Args:
        run_oracle_sql: Fixture to execute a SQL script.
    """
    try:
        result = run_oracle_sql("dg_apply_lag.sql")
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    stats_query = _query_with_columns(result, EXPECTED_LAG_COLUMNS)
    assert stats_query is not None, f"dg_apply_lag.sql did not return stats query with columns {sorted(EXPECTED_LAG_COLUMNS)}"

    process_query = _query_with_columns(result, EXPECTED_PROCESS_COLUMNS)
    assert process_query is not None, f"dg_apply_lag.sql did not return process query with columns {sorted(EXPECTED_PROCESS_COLUMNS)}"


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
