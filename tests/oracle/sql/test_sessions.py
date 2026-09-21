"""Integration test for oracle/sql/sessions.sql."""

from __future__ import annotations

import pytest

from tests.oracle.blocking import session_sid
from tests.oracle.script_runner import oracle_connection, run_script


@pytest.mark.oracle
def test_sessions_includes_current_sid(oracle_settings) -> None:
    """List the SID of the connection that runs the script."""
    with oracle_connection(oracle_settings) as connection:
        sid = session_sid(connection)
        result = run_script(connection, "sessions.sql")
    assert result.queries
    sids = [int(value) for value in result.queries[0].values("sid") if value is not None]
    assert sid in sids
