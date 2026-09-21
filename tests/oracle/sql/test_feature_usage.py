"""Integration test for oracle/sql/feature_usage.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_feature_usage(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute feature_usage.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "feature_usage.sql")
