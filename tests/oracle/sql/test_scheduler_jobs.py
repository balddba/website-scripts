"""Integration test for oracle/sql/scheduler_jobs.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_scheduler_jobs(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute scheduler_jobs.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "scheduler_jobs.sql")
