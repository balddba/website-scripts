"""Integration test for oracle/sql/locks.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import sid_values


@pytest.mark.oracle
def test_locks(run_oracle_sql, blocking_lock) -> None:
    """Show a TM or TX lock for the induced blocker or waiter."""
    result = run_oracle_sql("locks.sql")
    sids = sid_values(result)
    assert blocking_lock.blocker_sid in sids or blocking_lock.waiter_sid in sids
