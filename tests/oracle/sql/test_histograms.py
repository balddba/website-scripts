"""Integration test for oracle/sql/histograms.sql."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import oracledb
import pytest

from tests.oracle.script_runner import ScriptResult, oracle_connection, quote_ident
from tests.oracle.sql.harness import _is_environment_limitation

HISTOGRAM_TABLE = "WS_SQLTEST_HISTOGRAM"


@pytest.mark.oracle
def test_histograms_reports_seeded_skew(run_oracle_sql, oracle_settings) -> None:
    """Build skewed data and verify histogram summary and endpoints."""
    with seeded_histogram(oracle_settings) as (schema, table):
        try:
            result = run_oracle_sql("histograms.sql", args=[schema, table, "PAYLOAD"])
        except oracledb.DatabaseError as exc:
            if _is_environment_limitation(exc):
                pytest.skip(str(exc).split("\n", maxsplit=1)[0])
            raise

        assert _has_row(
            result,
            {"OWNER": schema, "TABLE_NAME": table, "COLUMN_NAME": "PAYLOAD", "NUM_BUCKETS": 2},
        )
        assert _has_row(result, {"OWNER": schema, "TABLE_NAME": table, "COLUMN_NAME": "PAYLOAD"}, "ENDPOINT_NUMBER")


@contextmanager
def seeded_histogram(oracle_settings) -> Iterator[tuple[str, str]]:
    """Create skewed column data and gather a two-bucket histogram."""
    schema = quote_ident(oracle_settings.schema_name)
    target = f"{schema}.{HISTOGRAM_TABLE}"
    try:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_table(cursor, target)
            cursor.execute(f"CREATE TABLE {target} (id NUMBER PRIMARY KEY, payload VARCHAR2(20))")
            cursor.execute(
                f"""
                INSERT INTO {target} (id, payload)
                SELECT LEVEL, CASE WHEN LEVEL <= 95 THEN 'common' ELSE 'rare' END
                FROM dual
                CONNECT BY LEVEL <= 100
                """
            )
            connection.commit()
            cursor.callproc(
                "DBMS_STATS.GATHER_TABLE_STATS",
                keyword_parameters={
                    "ownname": schema,
                    "tabname": HISTOGRAM_TABLE,
                    "method_opt": "FOR COLUMNS SIZE 2 payload",
                },
            )
        yield schema, HISTOGRAM_TABLE
    finally:
        with oracle_connection(oracle_settings) as connection, connection.cursor() as cursor:
            _drop_table(cursor, target)


def _drop_table(cursor: oracledb.Cursor, target: str) -> None:
    """Drop the histogram fixture table if it exists."""
    try:
        cursor.execute(f"DROP TABLE {target} PURGE")
    except oracledb.DatabaseError as exc:
        if "ORA-00942" not in str(exc):
            raise


def _has_row(result: ScriptResult, expected: dict[str, object], required: str | None = None) -> bool:
    """Return True when a result row contains the expected generated values."""
    columns = set(expected) | ({required} if required else set())
    for query in result.queries:
        if not columns <= {column.upper() for column in query.columns}:
            continue
        indexes = {column: query.column_index(column) for column in columns}
        if any(all(row[indexes[column]] == value for column, value in expected.items()) for row in query.rows):
            return True
    return False
