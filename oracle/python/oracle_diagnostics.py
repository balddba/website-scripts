#!/usr/bin/env python3
# ===============================================================================
#
# Script Name: oracle_diagnostics.py
# Title: Oracle database diagnostics
# Tags: Python, Diagnostics, Performance
# Purpose: Collect performance, storage, and catalog diagnostics from Oracle.
#
# Description:
#   Runs a broad set of database health checks and assembles their findings into
#   a consolidated diagnostic report with optional object filters.
#
# Parameters:
#   Command-line Oracle connection settings and diagnostic filters; use --help.
#
# Required Privileges:
#   - Read access to the Oracle catalog and dynamic performance views queried
#
# Output Format:
#   - Diagnostic report written to standard output or the requested output file
#
# Example Usage:
#   python oracle_diagnostics.py --help
#
# Author: Aaron Myers <aaron@balddba.com>
#
# ===============================================================================
"""Oracle database performance, storage, and catalog diagnostics analyzer."""

from __future__ import annotations

import sys
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import oracledb
import typer
from loguru import logger
from pydantic import BaseModel, Field, SecretStr, ValidationError


class OracleConnectionConfig(BaseModel):
    """Configuration for Oracle database connectivity and target filters.

    Attributes:
        hostname: Database host address or IP.
        port: Database listener port.
        service_name: Oracle service name.
        sid: Oracle System Identifier.
        username: Oracle database user.
        password: Secure password storage.
        is_sysdba: Whether to connect with SYSDBA privilege.
        owner: Optional schema owner filter.
        table_name: Optional table name filter.
        tablespace_name: Optional tablespace name filter.
    """

    model_config = {"extra": "forbid"}

    hostname: str = Field(default="localhost", description="Database hostname")
    port: int = Field(default=1521, description="Database port")
    service_name: str | None = Field(default=None, description="Oracle service name")
    sid: str | None = Field(default=None, description="Oracle SID")
    username: str = Field(..., description="Database username")
    password: SecretStr = Field(..., description="Database password")
    is_sysdba: bool = Field(default=False, description="Connect with SYSDBA mode")
    owner: str | None = Field(default=None, description="Schema owner filter")
    table_name: str | None = Field(default=None, description="Table name filter")
    tablespace_name: str | None = Field(default=None, description="Tablespace filter")


class WaitEventMetric(BaseModel):
    """Wait event statistics from V$SYSTEM_EVENT.

    Attributes:
        event_name: Name of the wait event.
        total_waits: Total number of waits for the event.
        total_timeouts: Total number of timeouts.
        time_waited_ms: Total time waited in milliseconds.
        avg_wait_ms: Average time waited in milliseconds per wait.
    """

    model_config = {"extra": "forbid"}

    event_name: str
    total_waits: int
    total_timeouts: int
    time_waited_ms: float
    avg_wait_ms: float


class StatMetric(BaseModel):
    """Generic statistic key-value pair from V$SYSSTAT.

    Attributes:
        name: Name of the statistic.
        value: Statistic value.
    """

    model_config = {"extra": "forbid"}

    name: str
    value: int


class BackgroundProcessInfo(BaseModel):
    """Information regarding active Oracle background processes.

    Attributes:
        process_name: Background process identifier (e.g. DBW0, LGWR, CKPT).
        description: Process description.
        os_pid: Operating system process ID.
        sid: Oracle session ID.
        serial_number: Oracle session serial number.
        session_status: Current status of the process session.
        current_wait_event: Current or last wait event.
        wait_state: State of the wait event.
    """

    model_config = {"extra": "forbid"}

    process_name: str
    description: str
    os_pid: str | None = None
    sid: int | None = None
    serial_number: int | None = None
    session_status: str | None = None
    current_wait_event: str | None = None
    wait_state: str | None = None


class TablespaceQuotaInfo(BaseModel):
    """User quota allocation and consumption per tablespace.

    Attributes:
        username: Schema username.
        tablespace_name: Target tablespace name.
        bytes_used: Space currently allocated in bytes.
        max_bytes: Maximum quota limit in bytes (-1 for unlimited).
        blocks_used: Number of database blocks used.
        max_blocks: Maximum block quota (-1 for unlimited).
        is_unlimited: True if quota is unlimited.
    """

    model_config = {"extra": "forbid"}

    username: str
    tablespace_name: str
    bytes_used: int
    max_bytes: int
    blocks_used: int
    max_blocks: int
    is_unlimited: bool


class BufferPoolMetric(BaseModel):
    """Buffer pool operational and sizing statistics.

    Attributes:
        pool_name: Buffer pool name (e.g. DEFAULT, KEEP, RECYCLE).
        block_size_bytes: Block size in bytes.
        set_size_buffers: Number of buffers in the pool set.
        physical_reads: Physical block reads.
        physical_writes: Physical block writes.
        free_buffer_wait: Number of free buffer wait occurrences.
        buffer_busy_wait: Number of buffer busy wait occurrences.
    """

    model_config = {"extra": "forbid"}

    pool_name: str
    block_size_bytes: int
    set_size_buffers: int
    physical_reads: int
    physical_writes: int
    free_buffer_wait: int
    buffer_busy_wait: int


class IndexStatInfo(BaseModel):
    """Index statistics and health metrics.

    Attributes:
        owner: Index schema owner.
        index_name: Name of the index.
        table_name: Associated table name.
        index_type: Index type (e.g. NORMAL, BITMAP, LOB).
        uniqueness: Uniqueness constraint (UNIQUE or NONUNIQUE).
        status: Index status (VALID or UNUSABLE).
        b_level: B-tree level depth.
        leaf_blocks: Number of leaf blocks.
        distinct_keys: Number of distinct indexed keys.
        clustering_factor: Index clustering factor relative to table blocks.
        num_rows: Total indexed rows.
        last_analyzed: Timestamp of last optimizer stats collection.
    """

    model_config = {"extra": "forbid"}

    owner: str
    index_name: str
    table_name: str
    index_type: str
    uniqueness: str
    status: str
    b_level: int | None = None
    leaf_blocks: int | None = None
    distinct_keys: int | None = None
    clustering_factor: int | None = None
    num_rows: int | None = None
    last_analyzed: datetime | None = None


class TableColumnInfo(BaseModel):
    """Table column definitions and data distribution statistics.

    Attributes:
        owner: Table owner.
        table_name: Table name.
        column_name: Column identifier.
        data_type: Oracle column data type.
        nullable: Whether column allows nulls.
        num_distinct: Number of distinct values.
        density: Column density factor for query optimization.
        num_nulls: Count of null values.
        histogram: Histogram type (e.g. NONE, FREQUENCY, HEIGHT BALANCED).
        avg_col_len: Average column data length in bytes.
    """

    model_config = {"extra": "forbid"}

    owner: str
    table_name: str
    column_name: str
    data_type: str
    nullable: str
    num_distinct: int | None = None
    density: float | None = None
    num_nulls: int | None = None
    histogram: str | None = None
    avg_col_len: int | None = None


class TableStorageInfo(BaseModel):
    """Table physical storage and row allocation metrics.

    Attributes:
        owner: Table owner schema.
        table_name: Table name.
        tablespace_name: Assigned tablespace.
        num_rows: Total estimated rows.
        blocks: Used database blocks.
        empty_blocks: Allocated but empty blocks.
        avg_space_bytes: Average free space in bytes per block.
        chain_cnt: Number of chained or migrated rows.
        avg_row_len: Average row length in bytes.
        segment_bytes: Total segment size in bytes.
        segment_extents: Number of allocated extents.
        last_analyzed: Timestamp of last statistics gathering.
    """

    model_config = {"extra": "forbid"}

    owner: str
    table_name: str
    tablespace_name: str | None = None
    num_rows: int | None = None
    blocks: int | None = None
    empty_blocks: int | None = None
    avg_space_bytes: int | None = None
    chain_cnt: int | None = None
    avg_row_len: int | None = None
    segment_bytes: int | None = None
    segment_extents: int | None = None
    last_analyzed: datetime | None = None


class TablePartitionInfo(BaseModel):
    """Table partition metadata and segment storage statistics.

    Attributes:
        owner: Partition owner schema.
        table_name: Table name.
        partition_name: Partition name.
        partition_position: Partition order position.
        tablespace_name: Tablespace where partition resides.
        num_rows: Number of rows in partition.
        blocks: Used blocks.
        compression: Compression status (ENABLED/DISABLED).
        high_value: Partition boundary value.
        last_analyzed: Timestamp when stats were collected.
    """

    model_config = {"extra": "forbid"}

    owner: str
    table_name: str
    partition_name: str
    partition_position: int
    tablespace_name: str | None = None
    num_rows: int | None = None
    blocks: int | None = None
    compression: str | None = None
    high_value: str | None = None
    last_analyzed: datetime | None = None


class HistogramInfo(BaseModel):
    """Column histogram distribution details and bucket count.

    Attributes:
        owner: Schema owner.
        table_name: Table name.
        column_name: Column identifier.
        histogram_type: Type of histogram (e.g. FREQUENCY, TOP-FREQUENCY, HYBRID).
        num_buckets: Number of histogram buckets.
        num_distinct: Number of distinct values.
        num_nulls: Number of null values.
        sample_size: Sample size used for histogram calculation.
    """

    model_config = {"extra": "forbid"}

    owner: str
    table_name: str
    column_name: str
    histogram_type: str
    num_buckets: int
    num_distinct: int | None = None
    num_nulls: int | None = None
    sample_size: int | None = None


class LobSegmentInfo(BaseModel):
    """LOB segment storage, chunking, and physical allocation info.

    Attributes:
        owner: Schema owner.
        table_name: Parent table name.
        column_name: LOB column name.
        segment_name: LOB segment name.
        tablespace_name: Tablespace storing the LOB.
        in_row: Whether inline storage is enabled (YES/NO).
        chunk_bytes: LOB chunk size in bytes.
        retention: Retention setting or PCTVERSION.
        cache: Cache setting (YES/NO).
        segment_bytes: Total physical LOB segment size in bytes.
        segment_extents: Number of allocated extents.
    """

    model_config = {"extra": "forbid"}

    owner: str
    table_name: str
    column_name: str
    segment_name: str
    tablespace_name: str | None = None
    in_row: str = "YES"
    chunk_bytes: int | None = None
    retention: str | None = None
    cache: str | None = None
    segment_bytes: int | None = None
    segment_extents: int | None = None


class RedoLogInfo(BaseModel):
    """Online redo log file and group status.

    Attributes:
        group_number: Log group number.
        thread_number: Redo log thread number.
        sequence_number: Log sequence number.
        size_bytes: Size of the redo log in bytes.
        members: Number of log multiplexed members.
        status: Status (CURRENT, ACTIVE, INACTIVE, UNUSED).
        archived: Archive status (YES/NO).
        first_time: First SCN timestamp for this log.
        member_paths: File paths of log group members.
    """

    model_config = {"extra": "forbid"}

    group_number: int
    thread_number: int
    sequence_number: int
    size_bytes: int
    members: int
    status: str
    archived: str
    first_time: datetime | None = None
    member_paths: list[str] = Field(default_factory=list)


class DiagnosticsReport(BaseModel):
    """Consolidated diagnostic and performance analysis report.

    Attributes:
        sequential_reads: Sequential read wait statistics.
        log_file_syncs: Redo and log file sync metrics.
        buffer_queue_stats: Dirty buffer and checkpoint queue statistics.
        background_processes: Background process state and session metrics.
        user_quotas: Tablespace quota consumption per user.
        buffer_pool_stats: Buffer pool operational statistics.
        index_stats: Index health and structural metrics.
        column_stats: Column level optimizer statistics.
        table_storage: Table storage, block, and segment metrics.
        table_partitions: Partition level storage and sizing metrics.
        column_histograms: Histogram bucket distribution details.
        lob_segments: LOB segment storage and physical allocation metrics.
        redo_logs: Redo log file group sizing and status.
    """

    model_config = {"extra": "forbid"}

    sequential_reads: list[WaitEventMetric] = Field(default_factory=list)
    log_file_syncs: list[WaitEventMetric] = Field(default_factory=list)
    buffer_queue_stats: list[StatMetric] = Field(default_factory=list)
    background_processes: list[BackgroundProcessInfo] = Field(default_factory=list)
    user_quotas: list[TablespaceQuotaInfo] = Field(default_factory=list)
    buffer_pool_stats: list[BufferPoolMetric] = Field(default_factory=list)
    index_stats: list[IndexStatInfo] = Field(default_factory=list)
    column_stats: list[TableColumnInfo] = Field(default_factory=list)
    table_storage: list[TableStorageInfo] = Field(default_factory=list)
    table_partitions: list[TablePartitionInfo] = Field(default_factory=list)
    column_histograms: list[HistogramInfo] = Field(default_factory=list)
    lob_segments: list[LobSegmentInfo] = Field(default_factory=list)
    redo_logs: list[RedoLogInfo] = Field(default_factory=list)


class OracleDriver:
    """Manages connections and session lifecycle for Oracle database."""

    def __init__(self, config: OracleConnectionConfig) -> None:
        """Initialize driver with connection settings.

        Args:
            config (OracleConnectionConfig): Oracle connection settings and credentials.
        """
        self._config = config

    @contextmanager
    def session(self) -> Generator[oracledb.Connection, None, None]:
        """Open and yield an Oracle database connection.

        Yields:
            oracledb.Connection: Active database connection.

        Raises:
            oracledb.DatabaseError: If connection fails.
        """
        if self._config.service_name:
            dsn = oracledb.makedsn(
                self._config.hostname,
                self._config.port,
                service_name=self._config.service_name,
            )
        elif self._config.sid:
            dsn = oracledb.makedsn(
                self._config.hostname,
                self._config.port,
                sid=self._config.sid,
            )
        else:
            dsn = f"{self._config.hostname}:{self._config.port}"

        mode = oracledb.SYSDBA if (self._config.is_sysdba or self._config.username.upper() == "SYS") else 0
        password = self._config.password.get_secret_value()

        logger.bind(
            host=self._config.hostname,
            port=self._config.port,
            user=self._config.username,
        ).info("Connecting to Oracle database")

        try:
            with oracledb.connect(
                user=self._config.username,
                password=password,
                dsn=dsn,
                mode=mode,
            ) as conn:
                yield conn
        except oracledb.DatabaseError as exc:
            logger.bind(
                host=self._config.hostname,
                port=self._config.port,
                user=self._config.username,
            ).error("Database connection failed: {}", exc)
            raise


class OracleDiagnosticsAnalyzer:
    """Performs database diagnostics across performance, storage, and catalog views."""

    def __init__(
        self,
        driver: OracleDriver,
        owner: str | None = None,
        table_name: str | None = None,
        tablespace_name: str | None = None,
    ) -> None:
        """Initialize the diagnostics analyzer service.

        Args:
            driver (OracleDriver): Database session driver.
            owner (str | None): Optional schema owner filter.
            table_name (str | None): Optional table filter.
            tablespace_name (str | None): Optional tablespace filter.
        """
        self._driver = driver
        self._owner = owner.upper() if owner else None
        self._table_name = table_name.upper() if table_name else None
        self._tablespace_name = tablespace_name.upper() if tablespace_name else None

    def run_all(self) -> DiagnosticsReport:
        """Execute all diagnostics and return consolidated report.

        Returns:
            DiagnosticsReport: Complete diagnostic metrics.
        """
        with self._driver.session() as conn:
            return DiagnosticsReport(
                sequential_reads=self.analyze_sequential_reads(conn),
                log_file_syncs=self.analyze_log_file_syncs(conn),
                buffer_queue_stats=self.analyze_buffer_queue_stats(conn),
                background_processes=self.analyze_background_processes(conn),
                user_quotas=self.analyze_user_quotas(conn),
                buffer_pool_stats=self.analyze_buffer_pool_stats(conn),
                index_stats=self.analyze_index_stats(conn),
                column_stats=self.analyze_column_stats(conn),
                table_storage=self.analyze_table_storage(conn),
                table_partitions=self.analyze_partitions(conn),
                column_histograms=self.analyze_histograms(conn),
                lob_segments=self.analyze_lob_segments(conn),
                redo_logs=self.analyze_redo_logs(conn),
            )

    def analyze_sequential_reads(self, conn: oracledb.Connection) -> list[WaitEventMetric]:
        """Analyze sequential read and single block I/O wait statistics.

        Args:
            conn (oracledb.Connection): Active database connection.

        Returns:
            list[WaitEventMetric]: List of sequential read wait event statistics.
        """
        sql = """
            SELECT
                event,
                total_waits,
                total_timeouts,
                ROUND(time_waited_micro / 1000, 2) AS time_waited_ms,
                ROUND(average_wait * 10, 2) AS avg_wait_ms
            FROM v$system_event
            WHERE event IN (
                'db file sequential read',
                'db file scattered read',
                'direct path read',
                'direct path read temp'
            )
            ORDER BY time_waited_micro DESC
        """
        rows = self._execute_query(conn, sql, {})
        return [
            WaitEventMetric(
                event_name=str(r[0]),
                total_waits=int(r[1]),
                total_timeouts=int(r[2]),
                time_waited_ms=float(r[3]),
                avg_wait_ms=float(r[4]),
            )
            for r in rows
        ]

    def analyze_log_file_syncs(self, conn: oracledb.Connection) -> list[WaitEventMetric]:
        """Analyze redo log and log file sync wait events.

        Args:
            conn (oracledb.Connection): Active database connection.

        Returns:
            list[WaitEventMetric]: List of log file sync and write events.
        """
        sql = """
            SELECT
                event,
                total_waits,
                total_timeouts,
                ROUND(time_waited_micro / 1000, 2) AS time_waited_ms,
                ROUND(average_wait * 10, 2) AS avg_wait_ms
            FROM v$system_event
            WHERE event IN (
                'log file sync',
                'log file parallel write',
                'log buffer space',
                'log file switch (checkpoint incomplete)',
                'log file switch (archiving needed)'
            )
            ORDER BY time_waited_micro DESC
        """
        rows = self._execute_query(conn, sql, {})
        return [
            WaitEventMetric(
                event_name=str(r[0]),
                total_waits=int(r[1]),
                total_timeouts=int(r[2]),
                time_waited_ms=float(r[3]),
                avg_wait_ms=float(r[4]),
            )
            for r in rows
        ]

    def analyze_buffer_queue_stats(self, conn: oracledb.Connection) -> list[StatMetric]:
        """Analyze dirty buffer write queue and inspection statistics.

        Args:
            conn (oracledb.Connection): Active database connection.

        Returns:
            list[StatMetric]: Buffer queue performance metrics.
        """
        sql = """
            SELECT name, value
            FROM v$sysstat
            WHERE name IN (
                'dirty buffers inspected',
                'free buffer inspected',
                'free buffer waits',
                'write clones created in foreground',
                'buffer checkpoint writes',
                'DBWR checkpoint buffers written',
                'DBWR thread checkpoint buffers written',
                'DBWR make free requests',
                'DBWR free buffers found',
                'DBWR lru scans'
            )
            ORDER BY name
        """
        rows = self._execute_query(conn, sql, {})
        return [StatMetric(name=str(r[0]), value=int(r[1])) for r in rows]

    def analyze_background_processes(self, conn: oracledb.Connection) -> list[BackgroundProcessInfo]:
        """Analyze background processes and their session status.

        Args:
            conn (oracledb.Connection): Active database connection.

        Returns:
            list[BackgroundProcessInfo]: Background process details.
        """
        sql = """
            SELECT
                b.name,
                b.description,
                p.spid,
                s.sid,
                s.serial#,
                s.status,
                s.event,
                s.state
            FROM v$bgprocess b
            LEFT JOIN v$process p ON b.paddr = p.addr
            LEFT JOIN v$session s ON p.addr = s.paddr
            WHERE b.paddr != HEXTORAW('00')
            ORDER BY b.name
        """
        rows = self._execute_query(conn, sql, {})
        results: list[BackgroundProcessInfo] = []
        for r in rows:
            results.append(
                BackgroundProcessInfo(
                    process_name=str(r[0]),
                    description=str(r[1]),
                    os_pid=str(r[2]) if r[2] is not None else None,
                    sid=int(r[3]) if r[3] is not None else None,
                    serial_number=int(r[4]) if r[4] is not None else None,
                    session_status=str(r[5]) if r[5] is not None else None,
                    current_wait_event=str(r[6]) if r[6] is not None else None,
                    wait_state=str(r[7]) if r[7] is not None else None,
                )
            )
        return results

    def analyze_user_quotas(self, conn: oracledb.Connection) -> list[TablespaceQuotaInfo]:
        """Analyze user tablespace quota limits and consumption.

        Args:
            conn (oracledb.Connection): Active database connection.

        Returns:
            list[TablespaceQuotaInfo]: Tablespace quota allocations.
        """
        sql_dba = """
            SELECT
                username,
                tablespace_name,
                bytes,
                max_bytes,
                blocks,
                max_blocks
            FROM dba_ts_quotas
            WHERE (:username IS NULL OR UPPER(username) = :username)
              AND (:tablespace_name IS NULL OR UPPER(tablespace_name) = :tablespace_name)
            ORDER BY username, tablespace_name
        """
        sql_user = """
            SELECT
                USER AS username,
                tablespace_name,
                bytes,
                max_bytes,
                blocks,
                max_blocks
            FROM user_ts_quotas
            WHERE (:tablespace_name IS NULL OR UPPER(tablespace_name) = :tablespace_name)
            ORDER BY tablespace_name
        """
        params = {
            "username": self._owner,
            "tablespace_name": self._tablespace_name,
        }
        rows = self._query_with_fallback(conn, sql_dba, sql_user, params)
        results: list[TablespaceQuotaInfo] = []
        for r in rows:
            max_bytes = int(r[3]) if r[3] is not None else -1
            results.append(
                TablespaceQuotaInfo(
                    username=str(r[0]),
                    tablespace_name=str(r[1]),
                    bytes_used=int(r[2]) if r[2] is not None else 0,
                    max_bytes=max_bytes,
                    blocks_used=int(r[4]) if r[4] is not None else 0,
                    max_blocks=int(r[5]) if r[5] is not None else -1,
                    is_unlimited=(max_bytes == -1),
                )
            )
        return results

    def analyze_buffer_pool_stats(self, conn: oracledb.Connection) -> list[BufferPoolMetric]:
        """Analyze buffer pool sizing, block sizes, and wait statistics.

        Args:
            conn (oracledb.Connection): Active database connection.

        Returns:
            list[BufferPoolMetric]: Buffer pool performance metrics.
        """
        sql = """
            SELECT
                name,
                block_size,
                set_msize,
                physical_reads,
                physical_writes,
                free_buffer_wait,
                buffer_busy_wait
            FROM v$buffer_pool_statistics
            ORDER BY name
        """
        rows = self._execute_query(conn, sql, {})
        return [
            BufferPoolMetric(
                pool_name=str(r[0]),
                block_size_bytes=int(r[1]),
                set_size_buffers=int(r[2]),
                physical_reads=int(r[3]),
                physical_writes=int(r[4]),
                free_buffer_wait=int(r[5]),
                buffer_busy_wait=int(r[6]),
            )
            for r in rows
        ]

    def analyze_index_stats(self, conn: oracledb.Connection) -> list[IndexStatInfo]:
        """Analyze index statistics, b-tree levels, and clustering factors.

        Args:
            conn (oracledb.Connection): Active database connection.

        Returns:
            list[IndexStatInfo]: Index statistics.
        """
        sql_dba = """
            SELECT
                owner,
                index_name,
                table_name,
                index_type,
                uniqueness,
                status,
                blevel,
                leaf_blocks,
                distinct_keys,
                clustering_factor,
                num_rows,
                last_analyzed
            FROM dba_indexes
            WHERE (:owner IS NULL OR owner = :owner)
              AND (:table_name IS NULL OR table_name = :table_name)
            ORDER BY owner, table_name, index_name
        """
        sql_all = """
            SELECT
                owner,
                index_name,
                table_name,
                index_type,
                uniqueness,
                status,
                blevel,
                leaf_blocks,
                distinct_keys,
                clustering_factor,
                num_rows,
                last_analyzed
            FROM all_indexes
            WHERE (:owner IS NULL OR owner = :owner)
              AND (:table_name IS NULL OR table_name = :table_name)
            ORDER BY owner, table_name, index_name
        """
        params = {"owner": self._owner, "table_name": self._table_name}
        rows = self._query_with_fallback(conn, sql_dba, sql_all, params)
        results: list[IndexStatInfo] = []
        for r in rows:
            results.append(
                IndexStatInfo(
                    owner=str(r[0]),
                    index_name=str(r[1]),
                    table_name=str(r[2]),
                    index_type=str(r[3]),
                    uniqueness=str(r[4]),
                    status=str(r[5]),
                    b_level=int(r[6]) if r[6] is not None else None,
                    leaf_blocks=int(r[7]) if r[7] is not None else None,
                    distinct_keys=int(r[8]) if r[8] is not None else None,
                    clustering_factor=int(r[9]) if r[9] is not None else None,
                    num_rows=int(r[10]) if r[10] is not None else None,
                    last_analyzed=r[11] if isinstance(r[11], datetime) else None,
                )
            )
        return results

    def analyze_column_stats(self, conn: oracledb.Connection) -> list[TableColumnInfo]:
        """Analyze table column data types, distinct values, and histograms.

        Args:
            conn (oracledb.Connection): Active database connection.

        Returns:
            list[TableColumnInfo]: Table column statistics.
        """
        sql_dba = """
            SELECT
                owner,
                table_name,
                column_name,
                data_type,
                nullable,
                num_distinct,
                density,
                num_nulls,
                histogram,
                avg_col_len
            FROM dba_tab_columns
            WHERE (:owner IS NULL OR owner = :owner)
              AND (:table_name IS NULL OR table_name = :table_name)
            ORDER BY owner, table_name, column_id
        """
        sql_all = """
            SELECT
                owner,
                table_name,
                column_name,
                data_type,
                nullable,
                num_distinct,
                density,
                num_nulls,
                histogram,
                avg_col_len
            FROM all_tab_columns
            WHERE (:owner IS NULL OR owner = :owner)
              AND (:table_name IS NULL OR table_name = :table_name)
            ORDER BY owner, table_name, column_id
        """
        params = {"owner": self._owner, "table_name": self._table_name}
        rows = self._query_with_fallback(conn, sql_dba, sql_all, params)
        results: list[TableColumnInfo] = []
        for r in rows:
            results.append(
                TableColumnInfo(
                    owner=str(r[0]),
                    table_name=str(r[1]),
                    column_name=str(r[2]),
                    data_type=str(r[3]),
                    nullable=str(r[4]),
                    num_distinct=int(r[5]) if r[5] is not None else None,
                    density=float(r[6]) if r[6] is not None else None,
                    num_nulls=int(r[7]) if r[7] is not None else None,
                    histogram=str(r[8]) if r[8] is not None else None,
                    avg_col_len=int(r[9]) if r[9] is not None else None,
                )
            )
        return results

    def analyze_table_storage(self, conn: oracledb.Connection) -> list[TableStorageInfo]:
        """Analyze table physical space, block allocations, and row chaining.

        Args:
            conn (oracledb.Connection): Active database connection.

        Returns:
            list[TableStorageInfo]: Table storage metrics.
        """
        sql_dba = """
            SELECT
                t.owner,
                t.table_name,
                t.tablespace_name,
                t.num_rows,
                t.blocks,
                t.empty_blocks,
                t.avg_space,
                t.chain_cnt,
                t.avg_row_len,
                t.last_analyzed,
                s.segment_bytes,
                s.segment_extents
            FROM dba_tables t
            LEFT JOIN (
                SELECT owner, segment_name, SUM(bytes) AS segment_bytes, COUNT(*) AS segment_extents
                FROM dba_segments
                WHERE segment_type IN ('TABLE', 'TABLE PARTITION', 'TABLE SUBPARTITION')
                GROUP BY owner, segment_name
            ) s ON t.owner = s.owner AND t.table_name = s.segment_name
            WHERE (:owner IS NULL OR t.owner = :owner)
              AND (:table_name IS NULL OR t.table_name = :table_name)
            ORDER BY t.owner, t.table_name
        """
        sql_all = """
            SELECT
                owner,
                table_name,
                tablespace_name,
                num_rows,
                blocks,
                empty_blocks,
                avg_space,
                chain_cnt,
                avg_row_len,
                last_analyzed,
                NULL AS segment_bytes,
                NULL AS segment_extents
            FROM all_tables
            WHERE (:owner IS NULL OR owner = :owner)
              AND (:table_name IS NULL OR table_name = :table_name)
            ORDER BY owner, table_name
        """
        params = {"owner": self._owner, "table_name": self._table_name}
        rows = self._query_with_fallback(conn, sql_dba, sql_all, params)
        results: list[TableStorageInfo] = []
        for r in rows:
            results.append(
                TableStorageInfo(
                    owner=str(r[0]),
                    table_name=str(r[1]),
                    tablespace_name=str(r[2]) if r[2] is not None else None,
                    num_rows=int(r[3]) if r[3] is not None else None,
                    blocks=int(r[4]) if r[4] is not None else None,
                    empty_blocks=int(r[5]) if r[5] is not None else None,
                    avg_space_bytes=int(r[6]) if r[6] is not None else None,
                    chain_cnt=int(r[7]) if r[7] is not None else None,
                    avg_row_len=int(r[8]) if r[8] is not None else None,
                    last_analyzed=r[9] if isinstance(r[9], datetime) else None,
                    segment_bytes=int(r[10]) if r[10] is not None else None,
                    segment_extents=int(r[11]) if r[11] is not None else None,
                )
            )
        return results

    def analyze_partitions(self, conn: oracledb.Connection) -> list[TablePartitionInfo]:
        """Analyze table partition metadata, storage blocks, and high values.

        Args:
            conn (oracledb.Connection): Active database connection.

        Returns:
            list[TablePartitionInfo]: Partition storage and boundary metrics.
        """
        sql_dba = """
            SELECT
                table_owner,
                table_name,
                partition_name,
                partition_position,
                tablespace_name,
                num_rows,
                blocks,
                compression,
                high_value,
                last_analyzed
            FROM dba_tab_partitions
            WHERE (:owner IS NULL OR table_owner = :owner)
              AND (:table_name IS NULL OR table_name = :table_name)
            ORDER BY table_owner, table_name, partition_position
        """
        sql_all = """
            SELECT
                table_owner,
                table_name,
                partition_name,
                partition_position,
                tablespace_name,
                num_rows,
                blocks,
                compression,
                high_value,
                last_analyzed
            FROM all_tab_partitions
            WHERE (:owner IS NULL OR table_owner = :owner)
              AND (:table_name IS NULL OR table_name = :table_name)
            ORDER BY table_owner, table_name, partition_position
        """
        params = {"owner": self._owner, "table_name": self._table_name}
        rows = self._query_with_fallback(conn, sql_dba, sql_all, params)
        results: list[TablePartitionInfo] = []
        for r in rows:
            results.append(
                TablePartitionInfo(
                    owner=str(r[0]),
                    table_name=str(r[1]),
                    partition_name=str(r[2]),
                    partition_position=int(r[3]),
                    tablespace_name=str(r[4]) if r[4] is not None else None,
                    num_rows=int(r[5]) if r[5] is not None else None,
                    blocks=int(r[6]) if r[6] is not None else None,
                    compression=str(r[7]) if r[7] is not None else None,
                    high_value=str(r[8]).strip() if r[8] is not None else None,
                    last_analyzed=r[9] if isinstance(r[9], datetime) else None,
                )
            )
        return results

    def analyze_histograms(self, conn: oracledb.Connection) -> list[HistogramInfo]:
        """Analyze column histograms and bucket distribution.

        Args:
            conn (oracledb.Connection): Active database connection.

        Returns:
            list[HistogramInfo]: Column histogram metadata.
        """
        sql_dba = """
            SELECT
                owner,
                table_name,
                column_name,
                histogram,
                num_buckets,
                num_distinct,
                num_nulls,
                sample_size
            FROM dba_tab_columns
            WHERE histogram != 'NONE'
              AND (:owner IS NULL OR owner = :owner)
              AND (:table_name IS NULL OR table_name = :table_name)
            ORDER BY owner, table_name, column_name
        """
        sql_all = """
            SELECT
                owner,
                table_name,
                column_name,
                histogram,
                num_buckets,
                num_distinct,
                num_nulls,
                sample_size
            FROM all_tab_columns
            WHERE histogram != 'NONE'
              AND (:owner IS NULL OR owner = :owner)
              AND (:table_name IS NULL OR table_name = :table_name)
            ORDER BY owner, table_name, column_name
        """
        params = {"owner": self._owner, "table_name": self._table_name}
        rows = self._query_with_fallback(conn, sql_dba, sql_all, params)
        results: list[HistogramInfo] = []
        for r in rows:
            results.append(
                HistogramInfo(
                    owner=str(r[0]),
                    table_name=str(r[1]),
                    column_name=str(r[2]),
                    histogram_type=str(r[3]),
                    num_buckets=int(r[4]) if r[4] is not None else 0,
                    num_distinct=int(r[5]) if r[5] is not None else None,
                    num_nulls=int(r[6]) if r[6] is not None else None,
                    sample_size=int(r[7]) if r[7] is not None else None,
                )
            )
        return results

    def analyze_lob_segments(self, conn: oracledb.Connection) -> list[LobSegmentInfo]:
        """Analyze LOB segments, in-row storage, and physical space usage.

        Args:
            conn (oracledb.Connection): Active database connection.

        Returns:
            list[LobSegmentInfo]: LOB segment storage metrics.
        """
        sql_dba = """
            SELECT
                l.owner,
                l.table_name,
                l.column_name,
                l.segment_name,
                l.tablespace_name,
                l.in_row,
                l.chunk,
                l.retention,
                l.cache,
                s.bytes,
                s.extents
            FROM dba_lobs l
            LEFT JOIN dba_segments s ON l.owner = s.owner AND l.segment_name = s.segment_name
            WHERE (:owner IS NULL OR l.owner = :owner)
              AND (:table_name IS NULL OR l.table_name = :table_name)
            ORDER BY l.owner, l.table_name, l.column_name
        """
        sql_all = """
            SELECT
                owner,
                table_name,
                column_name,
                segment_name,
                tablespace_name,
                in_row,
                chunk,
                retention,
                cache,
                NULL AS bytes,
                NULL AS extents
            FROM all_lobs
            WHERE (:owner IS NULL OR owner = :owner)
              AND (:table_name IS NULL OR table_name = :table_name)
            ORDER BY owner, table_name, column_name
        """
        params = {"owner": self._owner, "table_name": self._table_name}
        rows = self._query_with_fallback(conn, sql_dba, sql_all, params)
        results: list[LobSegmentInfo] = []
        for r in rows:
            results.append(
                LobSegmentInfo(
                    owner=str(r[0]),
                    table_name=str(r[1]),
                    column_name=str(r[2]),
                    segment_name=str(r[3]),
                    tablespace_name=str(r[4]) if r[4] is not None else None,
                    in_row=str(r[5]) if r[5] is not None else "YES",
                    chunk_bytes=int(r[6]) if r[6] is not None else None,
                    retention=str(r[7]) if r[7] is not None else None,
                    cache=str(r[8]) if r[8] is not None else None,
                    segment_bytes=int(r[9]) if r[9] is not None else None,
                    segment_extents=int(r[10]) if r[10] is not None else None,
                )
            )
        return results

    def analyze_redo_logs(self, conn: oracledb.Connection) -> list[RedoLogInfo]:
        """Analyze online redo log groups, multiplexing, and status.

        Args:
            conn (oracledb.Connection): Active database connection.

        Returns:
            list[RedoLogInfo]: Online redo log metrics.
        """
        sql_logs = """
            SELECT
                group#,
                thread#,
                sequence#,
                bytes,
                members,
                status,
                archived,
                first_time
            FROM v$log
            ORDER BY group#
        """
        sql_files = """
            SELECT group#, member
            FROM v$logfile
            ORDER BY group#
        """
        try:
            log_rows = self._execute_query(conn, sql_logs, {})
            file_rows = self._execute_query(conn, sql_files, {})
        except oracledb.DatabaseError as exc:
            logger.warning(
                "Could not query V$LOG / V$LOGFILE, skipping redo log analysis: {}",
                exc,
            )
            return []

        members_map: dict[int, list[str]] = {}
        for f in file_rows:
            grp = int(f[0])
            path = str(f[1])
            members_map.setdefault(grp, []).append(path)

        results: list[RedoLogInfo] = []
        for r in log_rows:
            grp_num = int(r[0])
            results.append(
                RedoLogInfo(
                    group_number=grp_num,
                    thread_number=int(r[1]),
                    sequence_number=int(r[2]),
                    size_bytes=int(r[3]),
                    members=int(r[4]),
                    status=str(r[5]),
                    archived=str(r[6]),
                    first_time=r[7] if isinstance(r[7], datetime) else None,
                    member_paths=members_map.get(grp_num, []),
                )
            )
        return results

    def _execute_query(self, conn: oracledb.Connection, sql: str, params: dict[str, Any]) -> list[tuple[Any, ...]]:
        """Execute a SQL query wrapped in safe error handling.

        Args:
            conn (oracledb.Connection): Active database connection.
            sql (str): SQL statement string.
            params (dict[str, Any]): Bind parameters.

        Returns:
            list[tuple[Any, ...]]: Result rows.

        Raises:
            oracledb.DatabaseError: If SQL execution fails.
        """
        with conn.cursor() as cursor:
            try:
                cursor.execute(sql, params)
                return cursor.fetchall()
            except oracledb.DatabaseError as exc:
                logger.error("Query execution failed: {}", exc)
                raise

    def _query_with_fallback(
        self,
        conn: oracledb.Connection,
        primary_sql: str,
        fallback_sql: str,
        params: dict[str, Any],
    ) -> list[tuple[Any, ...]]:
        """Execute query falling back from DBA_ to ALL_/USER_ views on ORA-00942.

        Args:
            conn (oracledb.Connection): Active connection.
            primary_sql (str): Primary DBA view query.
            fallback_sql (str): Fallback catalog view query.
            params (dict[str, Any]): Bind parameters.

        Returns:
            list[tuple[Any, ...]]: Result rows.

        Raises:
            oracledb.DatabaseError: If both queries fail.
        """
        with conn.cursor() as cursor:
            try:
                cursor.execute(primary_sql, params)
                return cursor.fetchall()
            except oracledb.DatabaseError as exc:
                err_obj = exc.args[0] if exc.args else None
                err_code = getattr(err_obj, "code", 0)
                if err_code == 942:
                    logger.warning("DBA view inaccessible (ORA-00942), falling back to ALL_/USER_ view")
                    try:
                        cursor.execute(fallback_sql, params)
                        return cursor.fetchall()
                    except oracledb.DatabaseError as fallback_exc:
                        logger.error("Fallback query failed: {}", fallback_exc)
                        raise
                logger.error("Catalog query failed: {}", exc)
                raise


def format_report_text(report: DiagnosticsReport) -> str:
    """Format full diagnostics report into a human-readable text document.

    Args:
        report (DiagnosticsReport): Compiled diagnostic report.

    Returns:
        str: Formatted report text.
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "=" * 85,
        " ORACLE DATABASE DIAGNOSTIC & PERFORMANCE REPORT",
        f" Generated: {now_str}",
        "=" * 85,
        "",
    ]

    # 1. Sequential Reads
    lines.append("--- 1. SEQUENTIAL READS & I/O WAIT EVENTS ---")
    if report.sequential_reads:
        lines.append(f"{'EVENT':<30} {'WAITS':<12} {'TIMEOUTS':<10} {'TIME (MS)':<15} {'AVG WAIT (MS)'}")
        lines.append("-" * 85)
        for w in report.sequential_reads:
            lines.append(f"{w.event_name:<30} {w.total_waits:<12} {w.total_timeouts:<10} {w.time_waited_ms:<15.2f} {w.avg_wait_ms:.2f}")
    else:
        lines.append("No sequential read wait events recorded.")
    lines.append("")

    # 2. Log File Sync
    lines.append("--- 2. LOG FILE SYNC & REDO WAITS ---")
    if report.log_file_syncs:
        lines.append(f"{'EVENT':<40} {'WAITS':<12} {'TIME (MS)':<15} {'AVG WAIT (MS)'}")
        lines.append("-" * 85)
        for lfs in report.log_file_syncs:
            lines.append(f"{lfs.event_name:<40} {lfs.total_waits:<12} {lfs.time_waited_ms:<15.2f} {lfs.avg_wait_ms:.2f}")
    else:
        lines.append("No log file sync wait events recorded.")
    lines.append("")

    # 3. Buffer Queue Statistics
    lines.append("--- 3. BUFFER QUEUE & DBWR STATISTICS ---")
    if report.buffer_queue_stats:
        lines.append(f"{'STATISTIC NAME':<45} {'VALUE'}")
        lines.append("-" * 85)
        for bq in report.buffer_queue_stats:
            lines.append(f"{bq.name:<45} {bq.value}")
    else:
        lines.append("No buffer queue statistics recorded.")
    lines.append("")

    # 4. Background Processes
    lines.append("--- 4. BACKGROUND PROCESS INFORMATION ---")
    if report.background_processes:
        lines.append(f"{'PROCESS':<10} {'OS PID':<10} {'SID/SERIAL':<14} {'STATUS':<10} {'CURRENT EVENT'}")
        lines.append("-" * 85)
        for bg in report.background_processes:
            sid_serial = f"{bg.sid},{bg.serial_number}" if bg.sid is not None else "N/A"
            os_pid = bg.os_pid or "N/A"
            status = bg.session_status or "N/A"
            event = bg.current_wait_event or bg.description
            lines.append(f"{bg.process_name:<10} {os_pid:<10} {sid_serial:<14} {status:<10} {event}")
    else:
        lines.append("No active background processes found.")
    lines.append("")

    # 5. User Quota on Tablespaces
    lines.append("--- 5. USER TABLESPACE QUOTAS ---")
    if report.user_quotas:
        lines.append(f"{'USERNAME':<20} {'TABLESPACE':<25} {'USED (MB)':<15} {'MAX (MB)'}")
        lines.append("-" * 85)
        for q in report.user_quotas:
            used_mb = q.bytes_used / (1024 * 1024)
            max_mb = "UNLIMITED" if q.is_unlimited else f"{q.max_bytes / (1024 * 1024):.2f}"
            lines.append(f"{q.username:<20} {q.tablespace_name:<25} {used_mb:<15.2f} {max_mb}")
    else:
        lines.append("No tablespace quotas found.")
    lines.append("")

    # 6. Buffer Pool Analysis
    lines.append("--- 6. BUFFER POOL STATISTICS ---")
    if report.buffer_pool_stats:
        lines.append(f"{'POOL NAME':<15} {'BLOCK SIZE':<12} {'SET SIZE':<12} {'PHYS READS':<15} {'PHYS WRITES':<15} {'BUSY WAITS'}")
        lines.append("-" * 85)
        for bp in report.buffer_pool_stats:
            lines.append(f"{bp.pool_name:<15} {bp.block_size_bytes:<12} {bp.set_size_buffers:<12} {bp.physical_reads:<15} {bp.physical_writes:<15} {bp.buffer_busy_wait}")
    else:
        lines.append("No buffer pool statistics found.")
    lines.append("")

    # 7. Index Stats Analysis
    lines.append("--- 7. INDEX STATISTICS ---")
    if report.index_stats:
        lines.append(f"{'OWNER':<15} {'TABLE':<20} {'INDEX NAME':<25} {'STATUS':<10} {'B-LEVEL':<8} {'LEAF BLKS':<10} {'ROWS'}")
        lines.append("-" * 85)
        for idx in report.index_stats:
            blevel = str(idx.b_level) if idx.b_level is not None else "N/A"
            leaf = str(idx.leaf_blocks) if idx.leaf_blocks is not None else "N/A"
            rows = str(idx.num_rows) if idx.num_rows is not None else "N/A"
            lines.append(f"{idx.owner:<15} {idx.table_name:<20} {idx.index_name:<25} {idx.status:<10} {blevel:<8} {leaf:<10} {rows}")
    else:
        lines.append("No index statistics found matching filter criteria.")
    lines.append("")

    # 8. Table Column Analysis
    lines.append("--- 8. TABLE COLUMN ANALYSIS ---")
    if report.column_stats:
        lines.append(f"{'TABLE':<20} {'COLUMN':<25} {'TYPE':<18} {'DISTINCT':<10} {'NULLS':<10} {'HISTOGRAM'}")
        lines.append("-" * 85)
        for col in report.column_stats:
            distinct = str(col.num_distinct) if col.num_distinct is not None else "N/A"
            nulls = str(col.num_nulls) if col.num_nulls is not None else "N/A"
            hist = col.histogram or "NONE"
            lines.append(f"{col.table_name:<20} {col.column_name:<25} {col.data_type:<18} {distinct:<10} {nulls:<10} {hist}")
    else:
        lines.append("No table columns found matching filter criteria.")
    lines.append("")

    # 9. Table Storage Analysis
    lines.append("--- 9. TABLE STORAGE ANALYSIS ---")
    if report.table_storage:
        lines.append(f"{'TABLE':<25} {'TABLESPACE':<18} {'ROWS':<10} {'BLOCKS':<10} {'SIZE (MB)':<12} {'CHAINED ROWS'}")
        lines.append("-" * 85)
        for tbl in report.table_storage:
            ts = tbl.tablespace_name or "N/A"
            rows = str(tbl.num_rows) if tbl.num_rows is not None else "N/A"
            blocks = str(tbl.blocks) if tbl.blocks is not None else "N/A"
            size_mb = f"{tbl.segment_bytes / (1024 * 1024):.2f}" if tbl.segment_bytes is not None else "N/A"
            chain = str(tbl.chain_cnt) if tbl.chain_cnt is not None else "N/A"
            lines.append(f"{tbl.table_name:<25} {ts:<18} {rows:<10} {blocks:<10} {size_mb:<12} {chain}")
    else:
        lines.append("No table storage metrics found matching filter criteria.")
    lines.append("")

    # 10. Table Partition Analysis
    lines.append("--- 10. TABLE PARTITION ANALYSIS ---")
    if report.table_partitions:
        lines.append(f"{'TABLE':<20} {'PARTITION':<20} {'POS':<5} {'TABLESPACE':<15} {'ROWS':<10} {'BLOCKS':<8} {'HIGH VALUE'}")
        lines.append("-" * 85)
        for part in report.table_partitions:
            ts = part.tablespace_name or "N/A"
            rows = str(part.num_rows) if part.num_rows is not None else "N/A"
            blocks = str(part.blocks) if part.blocks is not None else "N/A"
            hv = part.high_value or "N/A"
            if len(hv) > 20:
                hv = hv[:17] + "..."
            lines.append(f"{part.table_name:<20} {part.partition_name:<20} {part.partition_position:<5} {ts:<15} {rows:<10} {blocks:<8} {hv}")
    else:
        lines.append("No table partitions found matching filter criteria.")
    lines.append("")

    # 11. Column Histograms Analysis
    lines.append("--- 11. COLUMN HISTOGRAMS ANALYSIS ---")
    if report.column_histograms:
        lines.append(f"{'TABLE':<20} {'COLUMN':<25} {'HISTOGRAM TYPE':<20} {'BUCKETS':<10} {'DISTINCT':<10} {'NULLS'}")
        lines.append("-" * 85)
        for hist in report.column_histograms:
            distinct = str(hist.num_distinct) if hist.num_distinct is not None else "N/A"
            nulls = str(hist.num_nulls) if hist.num_nulls is not None else "N/A"
            lines.append(f"{hist.table_name:<20} {hist.column_name:<25} {hist.histogram_type:<20} {hist.num_buckets:<10} {distinct:<10} {nulls}")
    else:
        lines.append("No column histograms found matching filter criteria.")
    lines.append("")

    # 12. LOB Segment Analysis
    lines.append("--- 12. LOB SEGMENT STORAGE ANALYSIS ---")
    if report.lob_segments:
        lines.append(f"{'TABLE':<20} {'COLUMN':<20} {'LOB SEGMENT':<25} {'IN-ROW':<8} {'SIZE (MB)':<12} {'EXTENTS'}")
        lines.append("-" * 85)
        for lob in report.lob_segments:
            size_mb = f"{lob.segment_bytes / (1024 * 1024):.2f}" if lob.segment_bytes is not None else "N/A"
            exts = str(lob.segment_extents) if lob.segment_extents is not None else "N/A"
            lines.append(f"{lob.table_name:<20} {lob.column_name:<20} {lob.segment_name:<25} {lob.in_row:<8} {size_mb:<12} {exts}")
    else:
        lines.append("No LOB segments found matching filter criteria.")
    lines.append("")

    # 13. Online Redo Log Analysis
    lines.append("--- 13. ONLINE REDO LOG GROUPS ---")
    if report.redo_logs:
        lines.append(f"{'GRP':<5} {'THREAD':<8} {'SEQ#':<8} {'SIZE (MB)':<12} {'MEMBERS':<9} {'STATUS':<12} {'ARCHIVED'}")
        lines.append("-" * 85)
        for rlog in report.redo_logs:
            size_mb = f"{rlog.size_bytes / (1024 * 1024):.2f}"
            lines.append(f"{rlog.group_number:<5} {rlog.thread_number:<8} {rlog.sequence_number:<8} {size_mb:<12} {rlog.members:<9} {rlog.status:<12} {rlog.archived}")
            for path in rlog.member_paths:
                lines.append(f"    Member: {path}")
    else:
        lines.append("No online redo log files found.")

    lines.append("=" * 85)
    return "\n".join(lines)


class TyperApp(typer.Typer):
    """Typer application with parse_args support for programmatic parsing."""

    def parse_args(self, args: Sequence[str] | None = None) -> SimpleNamespace:
        """Parse arguments into a namespace for programmatic use.

        Args:
            args (Sequence[str] | None): Argument list to parse.

        Returns:
            SimpleNamespace: Parsed arguments as a namespace.
        """
        cmd = typer.main.get_command(self)
        ctx = cmd.make_context("oracle_diagnostics", list(args) if args is not None else sys.argv[1:])
        ns = SimpleNamespace(**ctx.params)
        if hasattr(ns, "table_name") and not hasattr(ns, "table"):
            ns.table = ns.table_name
        if hasattr(ns, "tablespace_name") and not hasattr(ns, "tablespace"):
            ns.tablespace = ns.tablespace_name
        if hasattr(ns, "json_output") and not hasattr(ns, "json"):
            ns.json = ns.json_output
        return ns


app = TyperApp(add_completion=False, help="Comprehensive Oracle performance, storage, and catalog diagnostics analyzer.")


@app.command()
def run(
    host: str = typer.Option("localhost", "--host", envvar="ORACLE_HOST", help="Oracle database host"),
    port: int = typer.Option(1521, "--port", envvar="ORACLE_PORT", help="Oracle database port"),
    service_name: str | None = typer.Option(None, "--service-name", envvar="ORACLE_SERVICE_NAME", help="Oracle service name"),
    sid: str | None = typer.Option(None, "--sid", envvar="ORACLE_SID", help="Oracle SID"),
    user: str | None = typer.Option(None, "--user", envvar="ORACLE_USER", help="Database username"),
    password: str | None = typer.Option(None, "--password", envvar="ORACLE_PASSWORD", help="Database password"),
    sysdba: bool = typer.Option(False, "--sysdba", help="Connect with SYSDBA privilege"),
    owner: str | None = typer.Option(None, "--owner", envvar="ORACLE_OWNER", help="Filter by schema owner"),
    table_name: str | None = typer.Option(None, "--table", envvar="ORACLE_TABLE", help="Filter by table name"),
    tablespace_name: str | None = typer.Option(None, "--tablespace", envvar="ORACLE_TABLESPACE", help="Filter by tablespace name"),
    json_output: bool = typer.Option(False, "--json", help="Output report in JSON format"),
    output: str | None = typer.Option(None, "--output", help="File path to save the output report"),
) -> int:
    """Comprehensive Oracle performance, storage, and catalog diagnostics analyzer.

    Args:
        host (str): Database host.
        port (int): Database port.
        service_name (str | None): Oracle service name.
        sid (str | None): Oracle SID.
        user (str | None): Database username.
        password (str | None): Database password.
        sysdba (bool): Connect with SYSDBA privilege.
        owner (str | None): Schema owner filter.
        table_name (str | None): Table name filter.
        tablespace_name (str | None): Tablespace name filter.
        json_output (bool): Output in JSON format.
        output (str | None): Output file path.

    Returns:
        int: Exit status code.
    """
    if not user:
        logger.error("Database username must be specified via --user or ORACLE_USER")
        return 1
    if not password:
        logger.error("Database password must be specified via --password or ORACLE_PASSWORD")
        return 1
    if not service_name and not sid:
        logger.error("Either --service-name or --sid must be specified (or via environment variables)")
        return 1

    try:
        config = OracleConnectionConfig(
            hostname=host,
            port=port,
            service_name=service_name,
            sid=sid,
            username=user,
            password=SecretStr(password),
            is_sysdba=sysdba,
            owner=owner,
            table_name=table_name,
            tablespace_name=tablespace_name,
        )
    except ValidationError as exc:
        logger.error("Configuration validation failed: {}", exc)
        return 1

    driver = OracleDriver(config)
    analyzer = OracleDiagnosticsAnalyzer(
        driver=driver,
        owner=config.owner,
        table_name=config.table_name,
        tablespace_name=config.tablespace_name,
    )

    try:
        report = analyzer.run_all()
    except oracledb.DatabaseError as exc:
        logger.error("Database error during diagnostic collection: {}", exc)
        return 1

    if json_output:
        output_text = report.model_dump_json(indent=2)
    else:
        output_text = format_report_text(report)

    if output:
        try:
            with open(output, "w", encoding="utf-8") as f:
                f.write(output_text)
            logger.info("Diagnostics report saved to {}", output)
        except OSError as exc:
            logger.error("Failed to write report to {}: {}", output, exc)
            return 1
    else:
        sys.stdout.write(output_text + "\n")

    return 0


def build_parser() -> TyperApp:
    """Build and return CLI argument parser.

    Returns:
        TyperApp: Configured parser.
    """
    return app


def main(argv: Sequence[str] | None = None) -> int:
    """CLI execution entrypoint.

    Args:
        argv (Sequence[str] | None): Optional command-line arguments.

    Returns:
        int: Exit status code.
    """
    try:
        args = list(argv) if argv is not None else None
        ret = app(args=args, standalone_mode=False)
        return 0 if ret is None else int(ret)
    except typer.Exit as exc:
        return exc.exit_code
    except Exception as exc:
        logger.error("{}", exc)
        return 1


if __name__ == "__main__":
    app()
