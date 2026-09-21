"""Integration test for oracle/sql/user_grant_copy.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_user_grant_copy(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute user_grant_copy.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "user_grant_copy.sql")
