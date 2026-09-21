"""Integration test for oracle/sql/object_ddl.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_object_ddl(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute object_ddl.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "object_ddl.sql")
