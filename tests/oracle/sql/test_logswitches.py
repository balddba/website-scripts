"""Integration test for oracle/sql/logswitches.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_logswitches(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute logswitches.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "logswitches.sql")
