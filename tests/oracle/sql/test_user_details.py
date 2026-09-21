"""Integration test for oracle/sql/user_details.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_user_details(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute user_details.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "user_details.sql")
