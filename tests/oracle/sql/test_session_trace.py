"""Integration test for oracle/sql/session_trace.sql."""

from __future__ import annotations

import pytest

from tests.oracle.script_runner import oracle_connection, run_script


@pytest.mark.oracle
def test_session_trace_enable_then_disable(oracle_settings) -> None:
    """Enable and disable SQL trace on the same session."""
    with oracle_connection(oracle_settings) as connection:
        run_script(connection, "session_trace.sql", args=["ENABLE"])
        run_script(connection, "session_trace.sql", args=["DISABLE"])
