"""Integration test for oracle/sql/ash_top_sql.sql."""

from __future__ import annotations

from collections.abc import Callable

import oracledb
import pytest

from tests.oracle.script_runner import ScriptResult, oracle_connection
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation


@pytest.mark.oracle
def test_ash_top_sql(
    run_oracle_sql: Callable[..., ScriptResult],
    oracle_settings: OracleTestSettings,
) -> None:
    """Execute ash_top_sql.sql after running a marked workload query.

    Args:
        run_oracle_sql (Callable[..., ScriptResult]): Fixture helper to run catalog scripts.
        oracle_settings (OracleTestSettings): Database connection settings.
    """
    with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
        try:
            cursor.execute("SELECT /* WS_ASH_TOP_TEST */ COUNT(*) FROM dual CONNECT BY LEVEL <= 1000")
        except oracledb.DatabaseError as exc:
            if _is_environment_limitation(exc):
                pytest.skip(str(exc).split("\n", maxsplit=1)[0])
            raise

    try:
        result = run_oracle_sql("ash_top_sql.sql", args=["30"])
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    assert result.queries, "ash_top_sql.sql produced no query results"

    matching = [
        query
        for query in result.queries
        if (
            {"SQL_ID", "EVENT"}.issubset({col.upper() for col in query.columns})
            or {"SQL_ID", "SAMPLE_COUNT"}.issubset({col.upper() for col in query.columns})
            or {"EVENT", "SAMPLE_COUNT"}.issubset({col.upper() for col in query.columns})
            or {"SQL_ID", "SAMPLES"}.issubset({col.upper() for col in query.columns})
        )
    ]
    assert matching, f"ash_top_sql.sql did not return expected diagnostic columns; got {result.queries[-1].columns}"
    query = matching[0]
    upper_cols = {col.upper() for col in query.columns}
    assert "SQL_ID" in upper_cols or "EVENT" in upper_cols
    assert "SAMPLE_COUNT" in upper_cols or "SAMPLES" in upper_cols

    if query.rows:
        sql_id_idx = query.column_index("SQL_ID")
        sample_count_idx = query.column_index("SAMPLE_COUNT")
        for row in query.rows:
            assert row[sql_id_idx] is not None or row[sample_count_idx] is not None
