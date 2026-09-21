"""Integration test for oracle/sql/redundant_indexes.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_redundant_indexes(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute redundant_indexes.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "redundant_indexes.sql")
