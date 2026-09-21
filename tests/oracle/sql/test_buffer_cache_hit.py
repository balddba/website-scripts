"""Integration test for oracle/sql/buffer_cache_hit.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_buffer_cache_hit(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute buffer_cache_hit.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "buffer_cache_hit.sql")
