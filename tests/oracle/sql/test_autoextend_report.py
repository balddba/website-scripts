"""Integration test for oracle/sql/autoextend_report.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_autoextend_report(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute autoextend_report.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "autoextend_report.sql")
