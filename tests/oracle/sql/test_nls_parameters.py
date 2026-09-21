"""Integration test for oracle/sql/nls_parameters.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_nls_parameters(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Execute nls_parameters.sql against the disposable test schema."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "nls_parameters.sql")
