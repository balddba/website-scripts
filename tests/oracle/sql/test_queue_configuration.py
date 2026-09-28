"""Integration test for oracle/sql/queue_configuration.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_queue_configuration(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute queue_configuration.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "queue_configuration.sql")
