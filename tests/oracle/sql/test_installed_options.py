"""Integration test for oracle/sql/installed_options.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_installed_options(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute installed_options.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "installed_options.sql")
