"""Integration test for oracle/sql/profiles.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_profiles(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute profiles.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "profiles.sql")
