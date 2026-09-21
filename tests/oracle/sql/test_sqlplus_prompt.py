"""Integration test for oracle/sql/sqlplus_prompt.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_sqlplus_prompt(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute sqlplus_prompt.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "sqlplus_prompt.sql")
