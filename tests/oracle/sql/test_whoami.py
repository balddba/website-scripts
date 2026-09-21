"""Integration test for oracle/sql/whoami.sql."""

from __future__ import annotations

import pytest

from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_whoami(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Return session identity rows including User and SID."""
    result = run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "whoami.sql")
    assert result.queries
    names = {str(value) for value in result.queries[0].values("name")}
    assert "User" in names
    assert "SID" in names
