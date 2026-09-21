"""Create disposable schema objects used by Oracle catalog tests."""

from __future__ import annotations

from dataclasses import dataclass

import oracledb
from loguru import logger

from tests.oracle.script_runner import quote_ident
from tests.oracle.settings import OracleTestSettings

LOCK_TABLE = "WS_SQLTEST_LOCK"
LOCK_INDEX = "WS_SQLTEST_LOCK_IX"
LOCK_SEQUENCE = "WS_SQLTEST_LOCK_SEQ"
LOCK_TRIGGER = "WS_SQLTEST_LOCK_TRG"
PART_TABLE = "WS_SQLTEST_PART"


@dataclass(frozen=True)
class FixtureObjects:
    """Names of objects created for catalog script tests.

    Attributes:
        schema (str): Owner of the fixture objects.
        table (str): Heap table used for locks, describe, and rebuild tests.
        index (str): Secondary index on the heap table.
        sequence (str): Sequence used by sequence.sql tests.
        trigger (str): Row trigger on the heap table.
        part_table (str | None): Partitioned table when creation succeeded.
        tablespace (str): Tablespace of the heap table.
        xplan_package (bool): True when the XPLAN package is available.
    """

    schema: str
    table: str
    index: str
    sequence: str
    trigger: str
    part_table: str | None
    tablespace: str
    xplan_package: bool


def bootstrap_fixture_objects(connection: oracledb.Connection, settings: OracleTestSettings) -> FixtureObjects:
    """Create the lock-probe table, index, sequence, trigger, and optional partition table.

    Args:
        connection (oracledb.Connection): Session with privilege to create objects in the test schema.
        settings (OracleTestSettings): Test connection settings.

    Returns:
        FixtureObjects: Created object names and tablespace.

    Raises:
        oracledb.DatabaseError: If required objects cannot be created.
    """
    schema = quote_ident(settings.schema_name)
    with connection.cursor() as cursor:
        _ensure_heap_table(cursor, schema)
        _ensure_index(cursor, schema)
        _ensure_sequence(cursor, schema)
        _ensure_trigger(cursor, schema)
        part_table = _ensure_part_table(cursor, schema)
        tablespace = _table_tablespace(cursor, schema, LOCK_TABLE)
        xplan_package = _xplan_exists(cursor)
        connection.commit()
    return FixtureObjects(
        schema=schema,
        table=LOCK_TABLE,
        index=LOCK_INDEX,
        sequence=LOCK_SEQUENCE,
        trigger=LOCK_TRIGGER,
        part_table=part_table,
        tablespace=tablespace,
        xplan_package=xplan_package,
    )


def _ensure_heap_table(cursor: oracledb.Cursor, schema: str) -> None:
    """Create the lock-probe table and seed one row when missing.

    Args:
        cursor (oracledb.Cursor): Open cursor.
        schema (str): Validated schema name.

    Raises:
        oracledb.DatabaseError: If CREATE or INSERT fails.
    """
    if _object_exists(cursor, schema, LOCK_TABLE, "TABLE"):
        _seed_lock_row(cursor, schema)
        return
    _execute(
        cursor,
        f"CREATE TABLE {schema}.{LOCK_TABLE} (id NUMBER PRIMARY KEY, payload VARCHAR2(64) NOT NULL)",
    )
    _seed_lock_row(cursor, schema)


def _seed_lock_row(cursor: oracledb.Cursor, schema: str) -> None:
    """Insert id=1 when the lock-probe table is empty.

    Args:
        cursor (oracledb.Cursor): Open cursor.
        schema (str): Validated schema name.

    Raises:
        oracledb.DatabaseError: If the seed insert fails.
    """
    _execute(cursor, f"SELECT COUNT(*) FROM {schema}.{LOCK_TABLE} WHERE id = 1")
    count = cursor.fetchone()
    if count and int(count[0]) > 0:
        return
    _execute(cursor, f"INSERT INTO {schema}.{LOCK_TABLE} (id, payload) VALUES (1, 'lock-row')")


def _ensure_index(cursor: oracledb.Cursor, schema: str) -> None:
    """Create a secondary index on the lock-probe table when missing.

    Args:
        cursor (oracledb.Cursor): Open cursor.
        schema (str): Validated schema name.

    Raises:
        oracledb.DatabaseError: If CREATE INDEX fails.
    """
    if _object_exists(cursor, schema, LOCK_INDEX, "INDEX"):
        return
    _execute(cursor, f"CREATE INDEX {schema}.{LOCK_INDEX} ON {schema}.{LOCK_TABLE} (payload)")


def _ensure_sequence(cursor: oracledb.Cursor, schema: str) -> None:
    """Create the probe sequence when missing.

    Args:
        cursor (oracledb.Cursor): Open cursor.
        schema (str): Validated schema name.

    Raises:
        oracledb.DatabaseError: If CREATE SEQUENCE fails.
    """
    if _object_exists(cursor, schema, LOCK_SEQUENCE, "SEQUENCE"):
        return
    _execute(cursor, f"CREATE SEQUENCE {schema}.{LOCK_SEQUENCE}")


def _ensure_trigger(cursor: oracledb.Cursor, schema: str) -> None:
    """Create a no-op row trigger on the lock-probe table.

    Args:
        cursor (oracledb.Cursor): Open cursor.
        schema (str): Validated schema name.

    Raises:
        oracledb.DatabaseError: If CREATE TRIGGER fails.
    """
    _execute(
        cursor,
        f"""
        CREATE OR REPLACE TRIGGER {schema}.{LOCK_TRIGGER}
        BEFORE INSERT ON {schema}.{LOCK_TABLE}
        FOR EACH ROW
        BEGIN
            NULL;
        END;
        """,
    )


def _ensure_part_table(cursor: oracledb.Cursor, schema: str) -> str | None:
    """Create a two-partition table when the user can create partitioned tables.

    Args:
        cursor (oracledb.Cursor): Open cursor.
        schema (str): Validated schema name.

    Returns:
        str | None: Partitioned table name, or None when creation is not allowed.
    """
    if _object_exists(cursor, schema, PART_TABLE, "TABLE"):
        return PART_TABLE
    try:
        _execute(
            cursor,
            f"""
            CREATE TABLE {schema}.{PART_TABLE} (
                id NUMBER,
                payload VARCHAR2(64)
            )
            PARTITION BY RANGE (id) (
                PARTITION p_low VALUES LESS THAN (100),
                PARTITION p_high VALUES LESS THAN (MAXVALUE)
            )
            """,
        )
    except oracledb.DatabaseError as exc:
        logger.bind(schema=schema).warning("partitioned_table_create_skipped err={}", exc)
        return None
    return PART_TABLE


def _table_tablespace(cursor: oracledb.Cursor, schema: str, table: str) -> str:
    """Return the tablespace name for a table.

    Args:
        cursor (oracledb.Cursor): Open cursor.
        schema (str): Validated schema name.
        table (str): Table name.

    Returns:
        str: Tablespace name, or empty string when it cannot be read.

    Raises:
        oracledb.DatabaseError: If the lookup query fails for a reason other than a missing view.
    """
    try:
        _execute(
            cursor,
            "SELECT tablespace_name FROM dba_tables WHERE owner = :owner AND table_name = :table_name",
            {"owner": schema, "table_name": table},
        )
        row = cursor.fetchone()
        if row and row[0]:
            return str(row[0])
    except oracledb.DatabaseError:
        _execute(
            cursor,
            "SELECT tablespace_name FROM user_tables WHERE table_name = :table_name",
            {"table_name": table},
        )
        row = cursor.fetchone()
        if row and row[0]:
            return str(row[0])
    return ""


def _xplan_exists(cursor: oracledb.Cursor) -> bool:
    """Return True when a package named XPLAN is visible.

    Args:
        cursor (oracledb.Cursor): Open cursor.

    Returns:
        bool: True if the package exists.
    """
    try:
        _execute(
            cursor,
            """
            SELECT COUNT(*)
            FROM all_objects
            WHERE object_name = 'XPLAN'
              AND object_type = 'PACKAGE'
            """,
        )
    except oracledb.DatabaseError:
        return False
    row = cursor.fetchone()
    return bool(row and int(row[0]) > 0)


def _object_exists(cursor: oracledb.Cursor, schema: str, name: str, object_type: str) -> bool:
    """Return True when the named object exists.

    Args:
        cursor (oracledb.Cursor): Open cursor.
        schema (str): Validated schema name.
        name (str): Object name.
        object_type (str): DBA_OBJECTS.OBJECT_TYPE value.

    Returns:
        bool: True if the object is present.
    """
    try:
        _execute(
            cursor,
            """
            SELECT COUNT(*)
            FROM dba_objects
            WHERE owner = :owner
              AND object_name = :object_name
              AND object_type = :object_type
            """,
            {"owner": schema, "object_name": name, "object_type": object_type},
        )
    except oracledb.DatabaseError:
        _execute(
            cursor,
            """
            SELECT COUNT(*)
            FROM all_objects
            WHERE owner = :owner
              AND object_name = :object_name
              AND object_type = :object_type
            """,
            {"owner": schema, "object_name": name, "object_type": object_type},
        )
    row = cursor.fetchone()
    return bool(row and int(row[0]) > 0)


def _execute(cursor: oracledb.Cursor, sql: str, binds: dict[str, object] | None = None) -> None:
    """Execute SQL with DatabaseError logging.

    Args:
        cursor (oracledb.Cursor): Open cursor.
        sql (str): Statement to run.
        binds (dict[str, object] | None): Named bind values.

    Raises:
        oracledb.DatabaseError: If execute fails.
    """
    try:
        if binds is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, binds)
    except oracledb.DatabaseError as exc:
        logger.bind(sql=sql[:200]).error("sql_execute_failed err={}", exc)
        raise
