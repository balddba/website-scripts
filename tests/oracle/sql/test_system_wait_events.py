"""Integration test for oracle/sql/system_wait_events.sql."""

from __future__ import annotations

from collections.abc import Callable

import oracledb
import pytest

from tests.oracle.script_runner import ScriptResult, oracle_connection
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation


@pytest.mark.oracle
def test_system_wait_events(
    run_oracle_sql: Callable[..., ScriptResult],
    oracle_settings: OracleTestSettings,
) -> None:
    """Execute system_wait_events.sql and verify non-idle wait event metrics.

    Args:
        run_oracle_sql (Callable[..., ScriptResult]): Fixture helper to run catalog scripts.
        oracle_settings (OracleTestSettings): Database connection settings.
    """
    with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
        try:
            cursor.execute("SELECT /* WS_SYSTEM_WAIT_TEST */ COUNT(*) FROM dual")
        except oracledb.DatabaseError as exc:
            if _is_environment_limitation(exc):
                pytest.skip(str(exc).split("\n", maxsplit=1)[0])
            raise

    try:
        result = run_oracle_sql("system_wait_events.sql")
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    assert result.queries, "system_wait_events.sql produced no query results"

    matching = [query for query in result.queries if {"EVENT", "WAIT_CLASS", "TOTAL_WAITS"}.issubset({col.upper() for col in query.columns})]
    assert matching, f"system_wait_events.sql did not return expected columns; got {result.queries[0].columns}"
    query = matching[0]

    upper_cols = {col.upper() for col in query.columns}
    assert any(col in upper_cols for col in ("TIME_WAITED_S", "TIME_WAITED_MS", "AVG_WAIT_MS")), f"Missing time waited column in {query.columns}"

    assert len(query.rows) > 0, "system_wait_events.sql returned zero rows"

    wait_class_idx = query.column_index("WAIT_CLASS")
    for row in query.rows:
        assert row[wait_class_idx] != "Idle", f"Found Idle wait class row: {row}"
