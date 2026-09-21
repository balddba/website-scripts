"""Integration test for oracle/sql/redo_logs.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_redo_logs(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute redo_logs.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "redo_logs.sql")
