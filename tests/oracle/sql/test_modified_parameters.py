"""Integration test for oracle/sql/modified_parameters.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_modified_parameters(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute modified_parameters.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "modified_parameters.sql")
