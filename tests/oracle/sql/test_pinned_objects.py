"""Integration test for oracle/sql/pinned_objects.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_pinned_objects(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute pinned_objects.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "pinned_objects.sql")
