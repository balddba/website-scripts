"""Integration test for oracle/sql/mview_refresh_groups.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_mview_refresh_groups(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute mview_refresh_groups.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "mview_refresh_groups.sql")
