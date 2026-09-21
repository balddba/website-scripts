"""Integration test for oracle/sql/session_io.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_session_io(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute session_io.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "session_io.sql")
