"""Integration test for oracle/sql/shared_pool.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_shared_pool(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute shared_pool.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "shared_pool.sql")
