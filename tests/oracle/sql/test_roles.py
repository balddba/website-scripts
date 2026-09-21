"""Integration test for oracle/sql/roles.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_roles(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute roles.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "roles.sql")
