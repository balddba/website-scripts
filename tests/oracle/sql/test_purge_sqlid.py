"""Integration test for oracle/sql/purge_sqlid.sql."""

from __future__ import annotations

import uuid

import oracledb
import pytest
from loguru import logger

from tests.oracle.script_runner import oracle_connection, run_script


@pytest.mark.oracle
def test_purge_sqlid(oracle_settings) -> None:
    """Purge a SQL_ID that this session just executed."""
    marker = uuid.uuid4().hex
    with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
        try:
            cursor.execute("SELECT 1 FROM dual WHERE 1 = 1 /* ws_sqltest_purge_" + marker + " */")
            cursor.execute(
                """
                SELECT sql_id
                FROM v$sql
                WHERE sql_text LIKE :pattern
                  AND ROWNUM = 1
                """,
                {"pattern": f"%ws_sqltest_purge_{marker}%"},
            )
        except oracledb.DatabaseError as exc:
            logger.error("sql_execute_failed err={}", exc)
            raise
        row = cursor.fetchone()
        if not row or not row[0]:
            pytest.skip("Could not capture a SQL_ID for the throwaway cursor")
        run_script(connection, "purge_sqlid.sql", args=[str(row[0])])
