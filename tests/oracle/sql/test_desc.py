"""Integration tests for oracle/sql/desc.sql."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import oracledb
import pytest

from tests.oracle.script_runner import QueryResult, ScriptResult, oracle_connection, quote_ident
from tests.oracle.sql.harness import _is_environment_limitation

DESC_TABLE = "WS_SQLTEST_DESC"
DESC_INDEX = "WS_SQLTEST_DESC_IX"
DESC_TRIGGER = "WS_SQLTEST_DESC_TRG"
DESC_VIEW = "WS_SQLTEST_DESC_V"
DESC_PART_TABLE = "WS_SQLTEST_DESC_PART"


@pytest.mark.oracle
def test_desc_reports_seeded_table_features(run_oracle_sql, oracle_settings) -> None:
    """Verify the populated report sections for a feature-rich heap table."""
    with seeded_desc_objects(oracle_settings) as target:
        result = _run_desc(run_oracle_sql, target)

        assert _property(result, "Owner") == oracle_settings.schema_name.upper()
        assert _property(result, "Table name") == DESC_TABLE
        assert _property(result, "Partitioned") == "NO"

        assert _has_row(result, {"SEGMENT_CATEGORY": "TABLE"})
        assert _has_row(result, {"SEGMENT_CATEGORY": "INDEX"})
        assert _has_row(result, {"SEGMENT_CATEGORY": "LOB"})
        assert _has_row(result, {"SEGMENT_CATEGORY": "LOB INDEX"})
        assert _has_row(result, {"SEGMENT_CATEGORY": "TOTAL"})

        assert _has_row(result, {"LOB_COLUMN": "NOTES"})
        assert _has_row(result, {"COLUMN_NAME": "ID", "NULLABLE": "NO"})
        assert _has_row(result, {"COLUMN_NAME": "PAYLOAD", "DATA_TYPE": "VARCHAR2(64 BYTE)"})
        assert _has_row(result, {"COLUMN_NAME": "PAYLOAD_UPPER", "VIRTUAL_COLUMN": "YES"})
        assert _has_row(result, {"STATS_COLUMN": "PAYLOAD"})

        assert _has_row(result, {"INDEX_NAME": DESC_INDEX, "INDEX_COLUMNS": "PAYLOAD, PARENT_ID"})
        assert _has_row(result, {"INDEX_NAME": DESC_INDEX}, required={"DISTINCT_KEYS", "INDEX_ANALYZED"})
        assert _has_row(result, {"CONSTRAINT_NAME": "WS_DESC_PK", "CONSTRAINT_TYPE": "PRIMARY KEY"})
        assert _has_row(result, {"CONSTRAINT_NAME": "WS_DESC_UK", "CONSTRAINT_TYPE": "UNIQUE"})
        assert _has_row(result, {"CONSTRAINT_NAME": "WS_DESC_FK", "CONSTRAINT_TYPE": "FOREIGN KEY"})
        assert _has_row(result, {"CONSTRAINT_NAME": "WS_DESC_CK", "CONSTRAINT_TYPE": "CHECK"})
        assert _has_row(result, {"FK_NAME": "WS_DESC_FK", "REFERENCED_TABLE": target})
        assert _has_row(result, {"FK_TABLE": target, "FK_NAME": "WS_DESC_FK"})
        assert _has_row(result, {"TRIGGER_NAME": DESC_TRIGGER, "TRIGGER_STATUS": "ENABLED"})
        assert _has_row(result, {"DEPENDENT_NAME": DESC_VIEW, "DEPENDENT_TYPE": "VIEW"})
        assert _has_row(result, {"MODIFICATION_PARTITION": "(table)"}, required={"INSERTS"})


@pytest.mark.oracle
def test_desc_reports_partition_details(run_oracle_sql, oracle_settings) -> None:
    """Verify partition metadata using a disposable range-partitioned table."""
    with seeded_partitioned_table(oracle_settings) as target:
        result = _run_desc(run_oracle_sql, target)

        assert _property(result, "Partitioned") == "YES"
        assert _has_row(result, {"PARTITION_NAME": "P_LOW", "PARTITION_POSITION": 1})
        assert _has_row(result, {"PARTITION_NAME": "P_HIGH", "PARTITION_POSITION": 2})
        assert _has_row(result, {"MODIFICATION_PARTITION": "P_LOW"}, required={"INSERTS"})
        assert _has_row(result, {"MODIFICATION_PARTITION": "P_HIGH"}, required={"INSERTS"})


@contextmanager
def seeded_desc_objects(oracle_settings) -> Iterator[str]:
    """Create a table whose features populate most desc.sql sections."""
    schema = quote_ident(oracle_settings.schema_name)
    target = f"{schema}.{DESC_TABLE}"
    try:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_desc_objects(cursor, schema)
            cursor.execute(
                f"""
                CREATE TABLE {target} (
                    id NUMBER NOT NULL,
                    parent_id NUMBER,
                    payload VARCHAR2(64) DEFAULT 'pending' NOT NULL,
                    payload_upper VARCHAR2(64) GENERATED ALWAYS AS (UPPER(payload)) VIRTUAL,
                    notes CLOB,
                    CONSTRAINT ws_desc_pk PRIMARY KEY (id),
                    CONSTRAINT ws_desc_uk UNIQUE (payload),
                    CONSTRAINT ws_desc_fk FOREIGN KEY (parent_id)
                        REFERENCES {target} (id) ON DELETE SET NULL,
                    CONSTRAINT ws_desc_ck CHECK (LENGTH(payload) > 2)
                )
                """
            )
            cursor.execute(f"CREATE INDEX {schema}.{DESC_INDEX} ON {target} (payload, parent_id)")
            cursor.execute(
                f"""
                CREATE OR REPLACE TRIGGER {schema}.{DESC_TRIGGER}
                BEFORE UPDATE OF payload ON {target}
                FOR EACH ROW
                BEGIN
                    :NEW.payload := TRIM(:NEW.payload);
                END;
                """
            )
            cursor.execute(f"CREATE OR REPLACE VIEW {schema}.{DESC_VIEW} AS SELECT id, payload FROM {target} WHERE payload IS NOT NULL")
            cursor.executemany(
                f"INSERT INTO {target} (id, parent_id, payload, notes) VALUES (:1, :2, :3, :4)",
                [
                    (1, None, "alpha", "first LOB value"),
                    (2, 1, "bravo", "second LOB value"),
                    (3, 1, "charlie", "third LOB value"),
                ],
            )
            connection.commit()
            cursor.callproc("DBMS_STATS.GATHER_TABLE_STATS", [schema, DESC_TABLE])
            cursor.execute(f"UPDATE {target} SET payload = 'delta' WHERE id = 3")
            connection.commit()
            cursor.callproc("DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO")
        yield target
    finally:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_desc_objects(cursor, schema)


@contextmanager
def seeded_partitioned_table(oracle_settings) -> Iterator[str]:
    """Create and seed a two-partition table for partition reports."""
    schema = quote_ident(oracle_settings.schema_name)
    target = f"{schema}.{DESC_PART_TABLE}"
    try:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_table(cursor, target)
            try:
                cursor.execute(
                    f"""
                    CREATE TABLE {target} (id NUMBER, payload VARCHAR2(64))
                    PARTITION BY RANGE (id) (
                        PARTITION p_low VALUES LESS THAN (100),
                        PARTITION p_high VALUES LESS THAN (MAXVALUE)
                    )
                    """
                )
            except oracledb.DatabaseError as exc:
                if _partitioning_unavailable(exc):
                    pytest.skip(str(exc).split("\n", maxsplit=1)[0])
                raise
            cursor.executemany(
                f"INSERT INTO {target} (id, payload) VALUES (:1, :2)",
                [(1, "low partition"), (101, "high partition")],
            )
            connection.commit()
            cursor.callproc("DBMS_STATS.GATHER_TABLE_STATS", [schema, DESC_PART_TABLE])
            cursor.execute(f"INSERT INTO {target} (id, payload) VALUES (2, 'low modification')")
            cursor.execute(f"INSERT INTO {target} (id, payload) VALUES (102, 'high modification')")
            connection.commit()
            cursor.callproc("DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO")
        yield target
    finally:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_table(cursor, target)


def _run_desc(run_oracle_sql, target: str) -> ScriptResult:
    """Run desc.sql and skip only when catalog access is unavailable."""
    try:
        return run_oracle_sql("desc.sql", args=[target])
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise


def _drop_desc_objects(cursor: oracledb.Cursor, schema: str) -> None:
    """Drop the view and table from this test, including interrupted runs."""
    _drop_object(cursor, f"DROP VIEW {schema}.{DESC_VIEW}", "ORA-00942")
    _drop_table(cursor, f"{schema}.{DESC_TABLE}")


def _drop_table(cursor: oracledb.Cursor, target: str) -> None:
    """Drop a test table when it exists."""
    _drop_object(cursor, f"DROP TABLE {target} PURGE", "ORA-00942")


def _drop_object(cursor: oracledb.Cursor, ddl: str, missing_code: str) -> None:
    """Execute teardown DDL while ignoring a missing-object error."""
    try:
        cursor.execute(ddl)
    except oracledb.DatabaseError as exc:
        if missing_code not in str(exc):
            raise


def _property(result: ScriptResult, name: str) -> object:
    """Return one value from the transposed table summary."""
    query = _query_with_columns(result, {"PROPERTY", "VALUE"})
    property_index = query.column_index("PROPERTY")
    value_index = query.column_index("VALUE")
    for row in query.rows:
        if row[property_index] == name:
            return row[value_index]
    pytest.fail(f"Summary property {name!r} was not returned by desc.sql")


def _has_row(
    result: ScriptResult,
    expected: dict[str, object],
    *,
    required: set[str] | None = None,
) -> bool:
    """Return True when a result row has expected values and columns."""
    columns = set(expected) | (required or set())
    try:
        query = _query_with_columns(result, columns)
    except AssertionError:
        return False
    indexes = {column: query.column_index(column) for column in columns}
    return any(all(row[indexes[column]] == value for column, value in expected.items()) for row in query.rows)


def _query_with_columns(result: ScriptResult, columns: set[str]) -> QueryResult:
    """Return the first result set containing all requested columns."""
    for query in result.queries:
        available = {column.upper() for column in query.columns}
        if columns <= available:
            return query
    pytest.fail(f"desc.sql did not return a result set with columns {sorted(columns)}")


def _partitioning_unavailable(exc: oracledb.DatabaseError) -> bool:
    """Return True when this database cannot create partitioned tables."""
    message = str(exc)
    return any(code in message for code in ("ORA-00439", "ORA-01031"))
