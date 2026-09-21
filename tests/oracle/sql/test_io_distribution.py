"""Integration test for oracle/sql/io_distribution.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_io_distribution(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute io_distribution.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "io_distribution.sql")
