"""Integration test for oracle/sql/xplan.display_cursor.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_xplan_display_cursor(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute xplan.display_cursor.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "xplan.display_cursor.sql")
