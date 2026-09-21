"""Integration test for oracle/sql/rollback_progress.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_rollback_progress(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute rollback_progress.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "rollback_progress.sql")
