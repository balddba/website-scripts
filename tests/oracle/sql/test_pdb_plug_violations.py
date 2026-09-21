"""Integration test for oracle/sql/pdb_plug_violations.sql."""

from __future__ import annotations

from collections.abc import Callable

import oracledb
import pytest

from tests.oracle.script_runner import ScriptResult
from tests.oracle.sql.harness import _is_environment_limitation


@pytest.mark.oracle
def test_pdb_plug_violations(run_oracle_sql: Callable[..., ScriptResult]) -> None:
    """Execute pdb_plug_violations.sql and assert plug-in violation report columns.

    Args:
        run_oracle_sql (Callable[..., ScriptResult]): Fixture that executes a script.
    """
    try:
        result = run_oracle_sql("pdb_plug_violations.sql")
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    assert result.statements, "pdb_plug_violations.sql did not execute any SQL statements"
    assert result.queries, "pdb_plug_violations.sql returned no query results"

    query = result.queries[0]
    columns = {col.upper() for col in query.columns}
    assert {"NAME", "TYPE", "MESSAGE", "STATUS"}.issubset(columns), f"pdb_plug_violations.sql missing expected columns; columns={columns}"
    assert "TIME" in columns or "TIME_STR" in columns, f"pdb_plug_violations.sql missing time column; columns={columns}"
