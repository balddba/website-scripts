"""Integration test for oracle/sql/ash_pga_temp.sql."""

from __future__ import annotations

from collections.abc import Callable

import oracledb
import pytest

from tests.oracle.script_runner import ScriptResult, oracle_connection
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation


@pytest.mark.oracle
def test_ash_pga_temp(
    run_oracle_sql: Callable[..., ScriptResult],
    oracle_settings: OracleTestSettings,
) -> None:
    """Execute ash_pga_temp.sql after running a memory/temp-allocating query.

    Args:
        run_oracle_sql (Callable[..., ScriptResult]): Fixture helper to run catalog scripts.
        oracle_settings (OracleTestSettings): Database connection settings.
    """
    with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
        try:
            cursor.execute(
                """
                SELECT /* WS_ASH_PGA_TEST */ id, payload
                FROM (
                    SELECT LEVEL AS id, RPAD('x', 1000, 'x') AS payload
                    FROM dual
                    CONNECT BY LEVEL <= 5000
                )
                ORDER BY payload DESC
                """
            )
            _ = cursor.fetchall()
        except oracledb.DatabaseError as exc:
            if _is_environment_limitation(exc):
                pytest.skip(str(exc).split("\n", maxsplit=1)[0])
            raise

    try:
        result = run_oracle_sql("ash_pga_temp.sql", args=["30"])
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    assert result.queries, "ash_pga_temp.sql produced no query results"

    matching = [query for query in result.queries if ({"SESSION_ID"}.issubset({c.upper() for c in query.columns}) or {"SQL_ID"}.issubset({c.upper() for c in query.columns})) and len(query.columns) > 1]
    assert matching, f"ash_pga_temp.sql did not return expected columns; got {result.queries[-1].columns}"
    query = matching[0]
    upper_cols = {c.upper() for c in query.columns}

    assert "SESSION_ID" in upper_cols or "SQL_ID" in upper_cols
    assert any(col in upper_cols for col in ("MAX_PGA_MB", "AVG_PGA_MB", "PGA_ALLOC_MB"))
    assert any(col in upper_cols for col in ("MAX_TEMP_MB", "AVG_TEMP_MB", "TEMP_ALLOC_MB"))
