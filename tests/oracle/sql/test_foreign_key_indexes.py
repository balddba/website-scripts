"""Integration test for oracle/sql/foreign_key_indexes.sql."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import oracledb
import pytest

from tests.oracle.script_runner import QueryResult, ScriptResult, oracle_connection, quote_ident
from tests.oracle.sql.harness import _is_environment_limitation

PARENT_TABLE = "WS_SQLTEST_FK_PARENT"
CHILD_TABLE = "WS_SQLTEST_FK_CHILD"
PARENT_INDEX = "WS_SQLTEST_FK_PARENT_PK"
CHILD_PK = "WS_SQLTEST_FK_CHILD_PK"
INDEXED_FK = "WS_SQLTEST_FK_INDEXED"
UNINDEXED_FK = "WS_SQLTEST_FK_UNINDEXED"
CHILD_FK_INDEX = "WS_SQLTEST_FK_CHILD_IX"


@pytest.mark.oracle
def test_foreign_key_indexes_distinguishes_index_cases(run_oracle_sql, oracle_settings) -> None:
    """Report an unindexed FK and an unusable parent index without false positives."""
    with seeded_foreign_keys(oracle_settings) as schema:
        result = _run_foreign_key_indexes(run_oracle_sql)

        missing_child_indexes = _query_with_columns(result, {"CONSTRAINT_NAME", "SUGGESTED_INDEX"})
        assert _has_row(
            missing_child_indexes,
            {
                "OWNER": schema,
                "TABLE_NAME": CHILD_TABLE,
                "CONSTRAINT_NAME": UNINDEXED_FK,
                "FK_COLUMNS": "UNINDEXED_PARENT_ID",
                "PARENT_TABLE": PARENT_TABLE,
                "FK_STATUS": "ENABLED",
                "DELETE_RULE": "CASCADE",
            },
        )
        assert UNINDEXED_FK in str(_value(missing_child_indexes, UNINDEXED_FK, "SUGGESTED_INDEX"))
        assert not _has_row(missing_child_indexes, {"CONSTRAINT_NAME": INDEXED_FK})

        parent_index_problems = _query_with_columns(result, {"FK_NAME", "PROBLEM"})
        assert _has_row(
            parent_index_problems,
            {
                "CHILD_OWNER": schema,
                "CHILD_TABLE": CHILD_TABLE,
                "FK_NAME": INDEXED_FK,
                "PARENT_TABLE": PARENT_TABLE,
                "INDEX_NAME": PARENT_INDEX,
                "INDEX_STATUS": "UNUSABLE",
                "PROBLEM": "INDEX UNUSABLE",
            },
        )
        assert _has_row(
            parent_index_problems,
            {"FK_NAME": UNINDEXED_FK, "INDEX_STATUS": "UNUSABLE", "PROBLEM": "INDEX UNUSABLE"},
        )


@contextmanager
def seeded_foreign_keys(oracle_settings) -> Iterator[str]:
    """Create indexed and unindexed child FKs against one parent key."""
    schema = quote_ident(oracle_settings.schema_name)
    parent = f"{schema}.{PARENT_TABLE}"
    child = f"{schema}.{CHILD_TABLE}"
    try:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_tables(cursor, schema)
            cursor.execute(
                f"""
                CREATE TABLE {parent} (
                    id NUMBER NOT NULL,
                    label VARCHAR2(64) NOT NULL
                )
                """
            )
            cursor.execute(f"CREATE UNIQUE INDEX {schema}.{PARENT_INDEX} ON {parent} (id)")
            cursor.execute(f"ALTER TABLE {parent} ADD CONSTRAINT ws_sqltest_fk_parent_c PRIMARY KEY (id) USING INDEX {schema}.{PARENT_INDEX}")
            cursor.execute(
                f"""
                CREATE TABLE {child} (
                    id NUMBER NOT NULL,
                    indexed_parent_id NUMBER,
                    unindexed_parent_id NUMBER,
                    payload VARCHAR2(64),
                    CONSTRAINT {CHILD_PK} PRIMARY KEY (id),
                    CONSTRAINT {INDEXED_FK} FOREIGN KEY (indexed_parent_id)
                        REFERENCES {parent} (id),
                    CONSTRAINT {UNINDEXED_FK} FOREIGN KEY (unindexed_parent_id)
                        REFERENCES {parent} (id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(f"CREATE INDEX {schema}.{CHILD_FK_INDEX} ON {child} (indexed_parent_id, payload)")
            cursor.execute(f"INSERT INTO {parent} (id, label) VALUES (1, 'parent row')")
            cursor.execute(f"INSERT INTO {child} (id, indexed_parent_id, unindexed_parent_id, payload) VALUES (1, 1, 1, 'child row')")
            connection.commit()
            cursor.execute(f"ALTER INDEX {schema}.{PARENT_INDEX} UNUSABLE")
        yield schema
    finally:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_tables(cursor, schema)


def _run_foreign_key_indexes(run_oracle_sql) -> ScriptResult:
    """Run the script and skip only when required catalog views are unavailable."""
    try:
        return run_oracle_sql("foreign_key_indexes.sql")
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise


def _drop_tables(cursor: oracledb.Cursor, schema: str) -> None:
    """Drop child before parent so foreign-key teardown is deterministic."""
    _drop_table(cursor, f"{schema}.{CHILD_TABLE}")
    _drop_table(cursor, f"{schema}.{PARENT_TABLE}")


def _drop_table(cursor: oracledb.Cursor, target: str) -> None:
    """Drop a fixture table if it exists."""
    try:
        cursor.execute(f"DROP TABLE {target} PURGE")
    except oracledb.DatabaseError as exc:
        if "ORA-00942" not in str(exc):
            raise


def _query_with_columns(result: ScriptResult, columns: set[str]) -> QueryResult:
    """Return the result set containing the requested columns."""
    for query in result.queries:
        if columns <= {column.upper() for column in query.columns}:
            return query
    pytest.fail(f"No result set contained columns {sorted(columns)}")


def _has_row(query: QueryResult, expected: dict[str, object]) -> bool:
    """Return True when one query row contains all expected values."""
    indexes = {column: query.column_index(column) for column in expected}
    return any(all(row[indexes[column]] == value for column, value in expected.items()) for row in query.rows)


def _value(query: QueryResult, constraint: str, column: str) -> object:
    """Return a column value from the row for one foreign-key constraint."""
    constraint_index = query.column_index("CONSTRAINT_NAME")
    value_index = query.column_index(column)
    for row in query.rows:
        if row[constraint_index] == constraint:
            return row[value_index]
    pytest.fail(f"Constraint {constraint} was not returned")
