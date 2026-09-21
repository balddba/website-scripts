"""Integration test for oracle/sql/unified_audit_summary.sql."""

from __future__ import annotations

import oracledb
import pytest

from tests.oracle.script_runner import QueryResult, ScriptResult
from tests.oracle.sql.harness import _is_environment_limitation

EXPECTED_AUDIT_COLUMNS = {
    "POLICY_NAME",
    "ENABLED_OPTION",
    "ENTITY_NAME",
    "SUCCESS",
    "FAILURE",
}


@pytest.mark.oracle
def test_unified_audit_summary(run_oracle_sql) -> None:
    """Execute unified_audit_summary.sql and verify unified audit policy columns.

    Args:
        run_oracle_sql: Fixture to execute a SQL script.
    """
    try:
        result = run_oracle_sql("unified_audit_summary.sql")
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    query = _query_with_columns(result, EXPECTED_AUDIT_COLUMNS)
    assert query is not None, f"unified_audit_summary.sql did not return query with columns {sorted(EXPECTED_AUDIT_COLUMNS)}"


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
