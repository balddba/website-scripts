"""Integration test for oracle/sql/database_links.sql."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import oracledb
import pytest

from tests.oracle.script_runner import ScriptResult, oracle_connection, quote_ident
from tests.oracle.sql.harness import _is_environment_limitation

DATABASE_LINK = "WS_SQLTEST_LOOPBACK"
REMOTE_VALUE = "database-link-round-trip"


@pytest.mark.oracle
def test_database_links_reports_working_loopback_link(run_oracle_sql, oracle_settings) -> None:
    """Create a loopback link, verify it works and is reported, then drop it."""
    with seeded_database_link(oracle_settings):
        try:
            result = run_oracle_sql("database_links.sql", args=[oracle_settings.user])
        except oracledb.DatabaseError as exc:
            if _is_environment_limitation(exc):
                pytest.skip(str(exc).split("\n", maxsplit=1)[0])
            raise

        row = _find_database_link(result)
        assert row["OWNER"] == oracle_settings.user.upper()
        assert str(row["DB_LINK"]).startswith(DATABASE_LINK)
        assert row["USERNAME"] == oracle_settings.user.upper()
        assert row["HOST"] == oracle_settings.connect
        assert row["CREATED"] is not None


@contextmanager
def seeded_database_link(oracle_settings) -> Iterator[None]:
    """Create a private link back to the configured test database."""
    username = quote_ident(oracle_settings.user)
    password = _quote_password(oracle_settings.password.get_secret_value())
    connect_string = _quote_string(oracle_settings.connect)

    try:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_database_link(cursor)
            cursor.execute(f"CREATE DATABASE LINK {DATABASE_LINK} CONNECT TO {username} IDENTIFIED BY {password} USING {connect_string}")
            cursor.execute(f"SELECT '{REMOTE_VALUE}' FROM dual@{DATABASE_LINK}")
            assert cursor.fetchone() == (REMOTE_VALUE,)
    except oracledb.DatabaseError as exc:
        if _cannot_create_loopback_link(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise

    try:
        yield
    finally:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_database_link(cursor)


def _drop_database_link(cursor: oracledb.Cursor) -> None:
    """Drop a loopback link left by this or an interrupted prior test."""
    try:
        cursor.execute(f"DROP DATABASE LINK {DATABASE_LINK}")
    except oracledb.DatabaseError as exc:
        if "ORA-02024" not in str(exc):
            raise


def _find_database_link(result: ScriptResult) -> dict[str, object]:
    """Return the report row for the seeded database link."""
    for query in result.queries:
        required = ("OWNER", "DB_LINK", "USERNAME", "HOST", "CREATED")
        try:
            indexes = {column: query.column_index(column) for column in required}
        except KeyError:
            continue
        for row in query.rows:
            link_name = str(row[indexes["DB_LINK"]])
            if link_name.startswith(DATABASE_LINK):
                return {column: row[index] for column, index in indexes.items()}
    pytest.fail(f"{DATABASE_LINK} was not returned by database_links.sql")


def _quote_password(value: str) -> str:
    """Quote a password for fixed-user database-link DDL."""
    return '"' + value.replace('"', '""') + '"'


def _quote_string(value: str) -> str:
    """Quote a value as an Oracle string literal."""
    return "'" + value.replace("'", "''") + "'"


def _cannot_create_loopback_link(exc: oracledb.DatabaseError) -> bool:
    """Return True for privileges or server-side connect-name limitations."""
    message = str(exc)
    return any(
        code in message
        for code in (
            "ORA-01031",
            "ORA-12154",
            "ORA-12514",
            "ORA-12541",
            "ORA-12545",
        )
    )
