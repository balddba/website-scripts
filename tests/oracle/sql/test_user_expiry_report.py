"""Integration test for oracle/sql/user_expiry_report.sql."""

from __future__ import annotations

import oracledb
import pytest

from tests.oracle.script_runner import QueryResult, ScriptResult
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation


@pytest.mark.oracle
def test_user_expiry_report(run_oracle_sql, oracle_settings: OracleTestSettings) -> None:
    """Execute user_expiry_report.sql and verify user expiry details for the connected user.

    Args:
        run_oracle_sql: Fixture to execute a SQL script.
        oracle_settings (OracleTestSettings): Validated Oracle test configuration.
    """
    try:
        result = run_oracle_sql("user_expiry_report.sql", args=["99999"])
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    expected_user = oracle_settings.user.upper()
    query = _find_user_query(result, expected_user)
    assert query is not None, f"user_expiry_report.sql did not return row for {expected_user}"

    user_index = query.column_index("USERNAME")
    status_index = query.column_index("ACCOUNT_STATUS")
    profile_index = query.column_index("PROFILE")
    expiry_index = query.column_index("EXPIRY_DATE")

    matching_rows = [row for row in query.rows if str(row[user_index]).upper() == expected_user]
    assert matching_rows, f"No row found with USERNAME == {expected_user}"
    row = matching_rows[0]
    assert row[status_index] is not None
    assert row[profile_index] is not None
    assert row[expiry_index] is not None


def _find_user_query(result: ScriptResult, expected_user: str) -> QueryResult | None:
    """Find a result query containing the expected user and required columns.

    Args:
        result (ScriptResult): Script execution result.
        expected_user (str): Upper-case username to find.

    Returns:
        QueryResult | None: Query result set containing the user, if found.
    """
    required_cols = {"USERNAME", "ACCOUNT_STATUS", "PROFILE", "EXPIRY_DATE"}
    for query in result.queries:
        available_cols = {col.upper() for col in query.columns}
        if required_cols <= available_cols:
            user_idx = query.column_index("USERNAME")
            if any(str(row[user_idx]).upper() == expected_user for row in query.rows):
                return query
    return None
