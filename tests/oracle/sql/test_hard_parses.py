"""Integration test for oracle/sql/hard_parses.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_hard_parses(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute hard_parses.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "hard_parses.sql")
