"""Integration test for oracle/sql/xplan.package.sql."""

from __future__ import annotations

import pytest

from tests.oracle.script_runner import oracle_connection
from tests.oracle.sql.harness import run_catalog_script


@pytest.mark.oracle
def test_xplan_package(run_oracle_sql, fixture_objects, oracle_settings) -> None:
    """Install XPLAN and verify every generated object is valid."""
    run_catalog_script(run_oracle_sql, fixture_objects, oracle_settings, "xplan.package.sql")

    with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT object_name, object_type, status
            FROM user_objects
            WHERE object_name IN ('XPLAN', 'XPLAN_OT', 'XPLAN_NTT')
            """
        )
        objects = {(name, object_type): status for name, object_type, status in cursor.fetchall()}

    assert objects == {
        ("XPLAN", "PACKAGE"): "VALID",
        ("XPLAN", "PACKAGE BODY"): "VALID",
        ("XPLAN_NTT", "TYPE"): "VALID",
        ("XPLAN_OT", "TYPE"): "VALID",
    }
