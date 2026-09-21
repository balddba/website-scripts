"""Integration test for oracle/sql/ash_wait_chains.sql."""

from __future__ import annotations

from collections.abc import Callable

import oracledb
import pytest

from tests.oracle.blocking import BlockingPair
from tests.oracle.script_runner import ScriptResult
from tests.oracle.sql.harness import _is_environment_limitation


@pytest.mark.oracle
def test_ash_wait_chains(
    run_oracle_sql: Callable[..., ScriptResult],
    blocking_lock: BlockingPair,
) -> None:
    """Execute ash_wait_chains.sql during an active blocking lock workload.

    Args:
        run_oracle_sql (Callable[..., ScriptResult]): Fixture helper to run catalog scripts.
        blocking_lock (BlockingPair): Fixture holding an induced row lock wait.
    """
    _ = blocking_lock.blocker_sid
    try:
        result = run_oracle_sql("ash_wait_chains.sql", args=["30"])
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    assert result.queries, "ash_wait_chains.sql produced no query results"

    matching = [query for query in result.queries if any(col in {c.upper() for c in query.columns} for col in ("CHAIN_COUNT", "BLOCKER", "EVENT", "INST_ID")) and len(query.columns) > 1]
    assert matching, f"ash_wait_chains.sql did not return wait chain columns; got {result.queries[-1].columns}"
    query = matching[0]
    upper_cols = {c.upper() for c in query.columns}
    assert any(col in upper_cols for col in ("CHAIN_COUNT", "BLOCKER", "EVENT", "INST_ID"))
