"""Integration test for oracle/sql/session_stats.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_session_stats(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute session_stats.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "session_stats.sql")
