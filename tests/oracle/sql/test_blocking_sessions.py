"""Integration test for oracle/sql/blocking_sessions.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import sid_values


@pytest.mark.oracle
def test_blocking_sessions(run_oracle_sql, blocking_lock) -> None:
    """Report both SIDs of an induced TX wait."""
    result = run_oracle_sql("blocking_sessions.sql")
    sids = sid_values(result)
    assert blocking_lock.blocker_sid in sids
    assert blocking_lock.waiter_sid in sids
