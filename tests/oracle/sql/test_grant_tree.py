"""Integration test for oracle/sql/grant_tree.sql."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import oracledb
import pytest

from tests.oracle.script_runner import QueryResult, ScriptResult, oracle_connection, quote_ident
from tests.oracle.sql.harness import _is_environment_limitation

GRANTEE = "WS_SQLTEST_GRANTEE"
GRANT_TABLE = "WS_SQLTEST_GRANTS"
GRANTEE_PASSWORD = '"WsSqltest_Grant1!"'


@pytest.mark.oracle
def test_grant_tree_reports_seeded_user_grants(run_oracle_sql, oracle_settings) -> None:
    """Create a small grant graph and verify every row in the reported tree."""
    if not oracle_settings.allow_instance_ddl:
        pytest.skip("ORACLE_TEST_ALLOW_INSTANCE_DDL is not enabled")

    with seeded_grants(oracle_settings) as owner:
        result = _run_grant_tree(run_oracle_sql)

        summary = _query_with_columns(result, {"GRANTEE", "GRANTEE_KIND", "REPORT_MODE"})
        assert summary.rows == [(GRANTEE, "USER", "ALL", "OPEN")]

        tree = _query_with_columns(result, {"GRANT_TREE", "NODE_TYPE", "OPTIONS", "GRANTOR"})
        assert len(tree.rows) == 4
        assert _has_tree_row(tree, GRANTEE, "USER", None, None)
        assert _has_tree_row(tree, "CREATE SESSION", "SYS", "admin=NO", None)
        assert _has_tree_row(
            tree,
            f"SELECT ON {owner}.{GRANT_TABLE}",
            "OBJECT",
            "grantable=NO",
            owner,
        )
        assert _has_tree_row(
            tree,
            f"UPDATE(PAYLOAD) ON {owner}.{GRANT_TABLE}",
            "COLUMN",
            "grantable=NO",
            owner,
        )


@contextmanager
def seeded_grants(oracle_settings) -> Iterator[str]:
    """Create one user, table, and a compact set of representative grants."""
    owner = quote_ident(oracle_settings.schema_name)
    target = f"{owner}.{GRANT_TABLE}"
    try:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_grant_fixtures(cursor, owner)
            try:
                cursor.execute(f"CREATE USER {GRANTEE} IDENTIFIED BY {GRANTEE_PASSWORD}")
            except oracledb.DatabaseError as exc:
                if _user_ddl_unavailable(exc):
                    pytest.skip(str(exc).split("\n", maxsplit=1)[0])
                raise
            cursor.execute(f"CREATE TABLE {target} (id NUMBER PRIMARY KEY, payload VARCHAR2(64) NOT NULL)")
            cursor.execute(f"INSERT INTO {target} (id, payload) VALUES (1, 'grant-tree-row')")
            cursor.execute(f"GRANT CREATE SESSION TO {GRANTEE}")
            cursor.execute(f"GRANT SELECT ON {target} TO {GRANTEE}")
            cursor.execute(f"GRANT UPDATE (payload) ON {target} TO {GRANTEE}")
            connection.commit()
        yield owner
    finally:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_grant_fixtures(cursor, owner)


def _run_grant_tree(run_oracle_sql) -> ScriptResult:
    """Run grant_tree.sql in ALL mode for the disposable grantee."""
    try:
        return run_oracle_sql("grant_tree.sql", args=[GRANTEE, "ALL"])
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise


def _drop_grant_fixtures(cursor: oracledb.Cursor, owner: str) -> None:
    """Remove the user first so its grants disappear before dropping the table."""
    _drop_object(cursor, f"DROP USER {GRANTEE} CASCADE", "ORA-01918")
    _drop_object(cursor, f"DROP TABLE {owner}.{GRANT_TABLE} PURGE", "ORA-00942")


def _drop_object(cursor: oracledb.Cursor, ddl: str, missing_code: str) -> None:
    """Run teardown DDL and ignore only the expected missing-object error."""
    try:
        cursor.execute(ddl)
    except oracledb.DatabaseError as exc:
        if missing_code not in str(exc):
            raise


def _query_with_columns(result: ScriptResult, columns: set[str]) -> QueryResult:
    """Return the result set containing all requested columns."""
    for query in result.queries:
        if columns <= {column.upper() for column in query.columns}:
            return query
    pytest.fail(f"No result set contained columns {sorted(columns)}")


def _has_tree_row(
    query: QueryResult,
    leaf: str,
    node_type: str,
    options: str | None,
    grantor: str | None,
) -> bool:
    """Match a tree row while ignoring its ASCII branch prefix."""
    tree_index = query.column_index("GRANT_TREE")
    type_index = query.column_index("NODE_TYPE")
    options_index = query.column_index("OPTIONS")
    grantor_index = query.column_index("GRANTOR")
    return any(str(row[tree_index]).endswith(leaf) and row[type_index] == node_type and row[options_index] == options and row[grantor_index] == grantor for row in query.rows)


def _user_ddl_unavailable(exc: oracledb.DatabaseError) -> bool:
    """Return True when the configured database cannot create local users."""
    message = str(exc)
    return any(code in message for code in ("ORA-01031", "ORA-65096"))
