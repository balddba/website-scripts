"""Shared assertions for MySQL catalog SQL tests."""

from __future__ import annotations

from collections.abc import Callable

from tests.mysql.script_runner import ScriptResult

EXPECTED_COLUMNS: dict[str, set[str]] = {
    "active_queries.sql": {"CONN_ID", "USER", "HOST", "DB", "COMMAND", "ELAPSED_SEC", "STATE", "SQL_TEXT"},
    "blocking_transactions.sql": {"WAITING_PID", "WAITING_QUERY", "WAIT_AGE", "LOCKED_TABLE", "LOCKED_INDEX", "WAITING_LOCK_MODE", "BLOCKING_PID", "BLOCKING_QUERY", "BLOCKING_TRX_AGE", "BLOCKING_LOCK_MODE"},
    "connection_stats.sql": {"METRIC", "VALUE"},
    "database_sizes.sql": {"SCHEMA_NAME", "TABLE_COUNT", "DATA_MB", "INDEX_MB", "TOTAL_MB", "TOTAL_GB"},
    "innodb_buffer_pool.sql": {"METRIC", "VALUE"},
    "innodb_engine_metrics.sql": {"CATEGORY", "METRIC", "VALUE"},
    "instance_info.sql": {"METRIC", "VALUE"},
    "memory_usage.sql": {"EVENT_NAME", "CURRENT_ALLOC_MB", "HIGH_WATER_MB", "CURRENT_ALLOC_COUNT", "TOTAL_ALLOCATIONS"},
    "table_io_stats.sql": {"SCHEMA_NAME", "TABLE_NAME", "TOTAL_IO_OPS", "TOTAL_WAIT_SEC", "READ_OPS", "READ_WAIT_SEC", "WRITE_OPS", "WRITE_WAIT_SEC"},
    "table_sizes.sql": {"SCHEMA_NAME", "TABLE_NAME", "ENGINE", "EST_ROWS", "DATA_MB", "INDEX_MB", "TOTAL_MB", "ROW_FORMAT"},
    "top_statements.sql": {"SCHEMA_NAME", "QUERY_PATTERN", "EXEC_COUNT", "TOTAL_SEC", "AVG_SEC", "MAX_SEC", "ROWS_EXAMINED", "ROWS_SENT", "NO_INDEX_USED_COUNT", "AVG_ROWS_EXAMINED"},
    "unused_indexes.sql": {"SCHEMA_NAME", "TABLE_NAME", "INDEX_NAME"},
}


def run_catalog_script(run_mysql_sql: Callable[[str], ScriptResult], script_name: str) -> ScriptResult:
    """Run one catalog script and verify its result contract."""
    result = run_mysql_sql(script_name)

    assert result.statements, f"{script_name} did not execute any SQL statements"
    assert result.queries, f"{script_name} produced no query results"
    for query in result.queries:
        assert query.columns, f"{script_name} returned a result set without columns"

    expected = EXPECTED_COLUMNS[script_name]
    actual = {column.upper() for column in result.queries[0].columns}
    assert expected == actual, f"{script_name} returned columns {sorted(actual)}, expected {sorted(expected)}"
    return result
