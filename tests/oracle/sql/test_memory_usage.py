"""Integration test for oracle/sql/memory_usage.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_memory_usage(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute memory_usage.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "memory_usage.sql")
