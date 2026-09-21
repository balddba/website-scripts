"""Integration test for oracle/sql/aq_queue.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_aq_queue(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute aq_queue.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "aq_queue.sql")
