"""Integration test for oracle/sql/undo_tuning.sql."""

from __future__ import annotations

import oracledb
import pytest

from tests.oracle.script_runner import QueryResult, ScriptResult
from tests.oracle.sql.harness import _is_environment_limitation

EXPECTED_UNDO_COLUMNS = {
    "BEGIN_TIME",
    "END_TIME",
    "UNDOBLKS",
    "TXNCOUNT",
    "MAXQUERYLEN",
    "SSOLDERRCNT",
}


@pytest.mark.oracle
def test_undo_tuning(run_oracle_sql) -> None:
    """Execute undo_tuning.sql and verify undo statistics columns.

    Args:
        run_oracle_sql: Fixture to execute a SQL script.
    """
    try:
        result = run_oracle_sql("undo_tuning.sql")
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    query = _query_with_columns(result, EXPECTED_UNDO_COLUMNS)
    assert query is not None, f"undo_tuning.sql did not return query with columns {sorted(EXPECTED_UNDO_COLUMNS)}"


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
