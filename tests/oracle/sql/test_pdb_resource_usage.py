"""Integration test for oracle/sql/pdb_resource_usage.sql."""

from __future__ import annotations

from collections.abc import Callable

import oracledb
import pytest

from tests.oracle.script_runner import ScriptResult
from tests.oracle.sql.harness import _is_environment_limitation


@pytest.mark.oracle
def test_pdb_resource_usage(run_oracle_sql: Callable[..., ScriptResult]) -> None:
    """Execute pdb_resource_usage.sql and assert expected metric columns.

    Args:
        run_oracle_sql (Callable[..., ScriptResult]): Fixture that executes a script.
    """
    try:
        result = run_oracle_sql("pdb_resource_usage.sql")
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    assert result.statements, "pdb_resource_usage.sql did not execute any SQL statements"
    assert result.queries, "pdb_resource_usage.sql returned no query results"

    query = result.queries[0]
    columns = {col.upper() for col in query.columns}
    assert "CON_ID" in columns, f"CON_ID column missing in pdb_resource_usage.sql; columns={columns}"
    assert "PDB_NAME" in columns or "CON_NAME" in columns, f"PDB_NAME column missing in pdb_resource_usage.sql; columns={columns}"

    cpu_columns = {"AVG_CPU_UTIL", "AVG_CPU_UTILIZATION", "CPU_UTILIZATION", "CPU_CONSUMED_MS", "CPU_CONSUMED_TIME"}
    session_columns = {
        "AVG_RUNNING_SESS",
        "AVG_WAITING_SESS",
        "AVG_RUNNING_SESSIONS",
        "AVG_WAITING_SESSIONS",
        "AVG_SESSION_COUNT",
    }
    assert bool(columns & cpu_columns) or bool(columns & session_columns), f"pdb_resource_usage.sql did not return CPU or session metrics; columns={columns}"
