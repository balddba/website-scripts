"""Integration test for oracle/sql/block_change_tracking.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_block_change_tracking(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute block_change_tracking.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "block_change_tracking.sql")
