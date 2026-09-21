"""Integration test for oracle/sql/blocking_sessions_monitor.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import sid_values


@pytest.mark.oracle
def test_blocking_sessions_monitor(run_oracle_sql, blocking_lock) -> None:
    """Include the induced blocker or waiter in the monitor report."""
    result = run_oracle_sql("blocking_sessions_monitor.sql")
    sids = set(sid_values(result))
    # The monitor concatenates SIDs into text columns on some queries.
    blob = " ".join(str(value) for query in result.queries for row in query.rows for value in row if value is not None)
    blob = f"{blob} {' '.join(str(sid) for sid in sids)}"
    assert str(blocking_lock.blocker_sid) in blob
    assert str(blocking_lock.waiter_sid) in blob
