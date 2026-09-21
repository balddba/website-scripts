"""Integration test for oracle/sql/unstable_plans.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_unstable_plans(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute unstable_plans.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "unstable_plans.sql")
