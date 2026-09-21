"""Integration test for oracle/sql/rman_backup_summary.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_rman_backup_summary(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute rman_backup_summary.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "rman_backup_summary.sql")
