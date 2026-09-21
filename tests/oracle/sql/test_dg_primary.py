"""Integration test for oracle/sql/dg_primary.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_dg_primary(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute dg_primary.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "dg_primary.sql")
