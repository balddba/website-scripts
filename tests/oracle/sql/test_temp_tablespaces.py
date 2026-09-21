"""Integration test for oracle/sql/temp_tablespaces.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_temp_tablespaces(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute temp_tablespaces.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "temp_tablespaces.sql")
