"""Integration test for oracle/sql/tables_without_pk.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_tables_without_pk(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute tables_without_pk.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "tables_without_pk.sql")
