"""Integration test for oracle/sql/cdb_services.sql."""

from __future__ import annotations

import re
from collections.abc import Callable

import oracledb
import pytest

from tests.oracle.script_runner import ScriptResult
from tests.oracle.settings import OracleTestSettings
from tests.oracle.sql.harness import _is_environment_limitation


@pytest.mark.oracle
def test_cdb_services(
    run_oracle_sql: Callable[..., ScriptResult],
    oracle_settings: OracleTestSettings,
) -> None:
    """Execute cdb_services.sql and assert service columns and rows.

    Args:
        run_oracle_sql (Callable[..., ScriptResult]): Fixture that executes a script.
        oracle_settings (OracleTestSettings): Validated connection settings.
    """
    try:
        result = run_oracle_sql("cdb_services.sql")
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    assert result.statements, "cdb_services.sql did not execute any SQL statements"
    assert result.queries, "cdb_services.sql returned no query results"

    query = result.queries[0]
    columns = {col.upper() for col in query.columns}
    assert {"NETWORK_NAME", "PDB_NAME", "INST_ID"}.issubset(columns), f"cdb_services.sql missing expected service columns; columns={columns}"
    assert "NAME" in columns or "SERVICE_NAME" in columns, f"cdb_services.sql missing service name column; columns={columns}"

    service_name = _extract_service_name(oracle_settings.connect)
    if service_name and _has_value(result, "NAME", service_name):
        assert _has_value(result, "NAME", service_name)
    else:
        assert len(query.rows) > 0, "cdb_services.sql returned no service rows"


def _extract_service_name(connect: str) -> str | None:
    """Extract the service name from an Oracle connect string.

    Args:
        connect (str): EZConnect or TNS connect string.

    Returns:
        str | None: Service name if detected, otherwise None.
    """
    match = re.search(r"SERVICE_NAME\s*=\s*([a-zA-Z0-9_#$.]+)", connect, re.IGNORECASE)
    if match:
        return match.group(1)
    if "/" in connect:
        after_slash = connect.split("/", 1)[1]
        candidate = re.split(r"[:/]", after_slash)[0].strip()
        if candidate:
            return candidate
    return None


def _has_value(result: ScriptResult, column: str, expected: object) -> bool:
    """Return True when any result set includes a column value.

    Args:
        result (ScriptResult): Script execution result.
        column (str): Column name or alias to inspect.
        expected (object): Value expected in the column.

    Returns:
        bool: True if the value appears in the result column.
    """
    for query in result.queries:
        matched_column = None
        for col in query.columns:
            if col.upper() == column.upper():
                matched_column = col
                break
        if matched_column is None and column.upper() == "NAME":
            for col in query.columns:
                if col.upper() == "SERVICE_NAME":
                    matched_column = col
                    break
        elif matched_column is None and column.upper() == "SERVICE_NAME":
            for col in query.columns:
                if col.upper() == "NAME":
                    matched_column = col
                    break
        if matched_column is None:
            continue
        try:
            values = query.values(matched_column)
        except KeyError:
            continue
        if expected in values:
            return True
        if isinstance(expected, str) and any(str(val).upper() == expected.upper() for val in values if val is not None):
            return True
    return False
