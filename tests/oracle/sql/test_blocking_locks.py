"""Integration test for oracle/sql/blocking_locks.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import sid_values


@pytest.mark.oracle
def test_blocking_locks(run_oracle_sql, blocking_lock) -> None:
    """Show the induced blocker and waiter in the lock tree."""
    result = run_oracle_sql("blocking_locks.sql")
    sids = sid_values(result)
    assert blocking_lock.blocker_sid in sids
    assert blocking_lock.waiter_sid in sids
