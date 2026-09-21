"""Integration test for oracle/sql/segment_space.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_segment_space(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute segment_space.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "segment_space.sql")
