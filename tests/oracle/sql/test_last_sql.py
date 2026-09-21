"""Integration test for oracle/sql/last_sql.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_last_sql(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute last_sql.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "last_sql.sql")
