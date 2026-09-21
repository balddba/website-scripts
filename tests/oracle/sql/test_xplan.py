"""Integration test for oracle/sql/xplan.sql."""

from __future__ import annotations

import oracledb
import pytest
from loguru import logger

from tests.oracle.script_runner import oracle_connection, run_script


@pytest.mark.oracle
def test_xplan(oracle_settings) -> None:
    """Display a plan after EXPLAIN PLAN FOR a trivial statement."""
    with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
        try:
            cursor.execute("EXPLAIN PLAN FOR SELECT 1 FROM dual")
        except oracledb.DatabaseError as exc:
            logger.error("sql_execute_failed err={}", exc)
            raise
        result = run_script(connection, "xplan.sql")
    assert result.queries
