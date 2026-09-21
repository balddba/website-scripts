"""Integration test for oracle/sql/redundant_constraints.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_redundant_constraints(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute redundant_constraints.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "redundant_constraints.sql")
