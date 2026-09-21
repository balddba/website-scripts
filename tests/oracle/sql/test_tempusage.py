"""Integration test for oracle/sql/tempusage.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_tempusage(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute tempusage.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "tempusage.sql")
