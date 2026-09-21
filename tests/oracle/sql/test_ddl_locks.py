"""Integration test for oracle/sql/ddl_locks.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_ddl_locks(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute ddl_locks.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "ddl_locks.sql")
