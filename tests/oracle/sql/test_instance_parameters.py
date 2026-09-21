"""Integration test for oracle/sql/instance_parameters.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_instance_parameters(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute instance_parameters.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "instance_parameters.sql")
