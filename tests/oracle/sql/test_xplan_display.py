"""Integration test for oracle/sql/xplan.display.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_xplan_display(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute xplan.display.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "xplan.display.sql")
