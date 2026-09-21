"""Integration test for oracle/sql/move_table_online.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_move_table_online(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute move_table_online.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "move_table_online.sql")
