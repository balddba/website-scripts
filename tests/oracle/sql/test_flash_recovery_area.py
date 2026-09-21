"""Integration test for oracle/sql/flash_recovery_area.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_flash_recovery_area(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute flash_recovery_area.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "flash_recovery_area.sql")
