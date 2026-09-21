"""Integration test for oracle/sql/userdiff.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_userdiff(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute userdiff.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "userdiff.sql")
