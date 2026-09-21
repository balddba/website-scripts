"""Integration test for oracle/sql/table_clustering.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_table_clustering(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute table_clustering.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "table_clustering.sql")
