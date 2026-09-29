#!/usr/bin/env python3
# ===============================================================================
#
# Script Name: oracle_system_metrics_diagnostics.py
# Title: Oracle system metrics diagnostics
# Tags: Python, Metrics, Performance
# Purpose: Diagnose Oracle CPU, I/O, cache, latch, and SQL parse activity.
#
# Description:
#   Collects system metrics, cache advice, I/O statistics, latch contention,
#   and high-parse SQL details with tuning recommendations.
#
# Parameters:
#   Command-line Oracle connection settings and report options; use --help.
#
# Required Privileges:
#   - Read access to the Oracle dynamic performance views queried
#
# Output Format:
#   - Diagnostic report written to standard output or the requested output file
#
# Example Usage:
#   python oracle_system_metrics_diagnostics.py --help
#
# Author: Aaron Myers <aaron@balddba.com>
#
# ===============================================================================
"""Oracle database system metrics and SQL parse diagnostics analyzer.

Provides diagnostics for buffer pool statistics with cache advice, CPU usage
and time model metrics, I/O statistics by tablespace and data file, latch contention
and misses, and high SQL parse rates with root-cause offending SQL diagnosis.
"""

from __future__ import annotations

import sys
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import oracledb
import typer
from loguru import logger
from pydantic import BaseModel, Field, SecretStr, ValidationError


class OracleConnectionConfig(BaseModel):
    """Configuration for Oracle database connectivity.

    Attributes:
        hostname: Database hostname or IP address.
        port: Database listener port.
        service_name: Oracle service name.
        sid: Oracle System Identifier.
        username: Oracle database user.
        password: Secure password storage.
        is_sysdba: Whether to connect with SYSDBA privilege.
    """

    model_config = {"extra": "forbid"}

    hostname: str = Field(default="localhost", description="Database hostname")
    port: int = Field(default=1521, description="Database port")
    service_name: str | None = Field(default=None, description="Oracle service name")
    sid: str | None = Field(default=None, description="Oracle SID")
    username: str = Field(..., description="Database username")
    password: SecretStr = Field(..., description="Database password")
    is_sysdba: bool = Field(default=False, description="Connect with SYSDBA mode")


class CacheAdviceEntry(BaseModel):
    """Buffer cache sizing advice projection from V$DB_CACHE_ADVICE.

    Attributes:
        pool_name: Name of buffer pool.
        block_size_bytes: Block size for this pool in bytes.
        size_factor: Sizing factor relative to current size (1.0 = current size).
        size_mb: Projected buffer pool size in megabytes.
        estd_physical_reads: Estimated number of physical reads at this size.
        estd_physical_read_factor: Estimated physical read factor relative to current.
        estd_physical_read_time_ms: Estimated physical read time in milliseconds.
    """

    model_config = {"extra": "forbid"}

    pool_name: str
    block_size_bytes: int
    size_factor: float
    size_mb: float
    estd_physical_reads: int
    estd_physical_read_factor: float
    estd_physical_read_time_ms: float = 0.0


class BufferPoolStat(BaseModel):
    """Buffer pool operational and sizing metrics.

    Attributes:
        pool_name: Buffer pool identifier (e.g. DEFAULT, KEEP, RECYCLE).
        block_size_bytes: Block size in bytes for the pool.
        size_mb: Total buffer pool size in megabytes.
        physical_reads: Number of physical data block reads.
        physical_writes: Number of physical data block writes.
        db_block_gets: Number of current block gets.
        consistent_gets: Number of consistent read gets.
        cache_hit_ratio_pct: Buffer cache hit ratio percentage.
        free_buffer_inspected: Total count of free buffers inspected system-wide.
        dirty_buffers_inspected: Total count of dirty buffers inspected system-wide.
        cache_advice: Cache advice projections from V$DB_CACHE_ADVICE.
    """

    model_config = {"extra": "forbid"}

    pool_name: str
    block_size_bytes: int
    size_mb: float
    physical_reads: int
    physical_writes: int
    db_block_gets: int
    consistent_gets: int
    cache_hit_ratio_pct: float
    free_buffer_inspected: int = 0
    dirty_buffers_inspected: int = 0
    cache_advice: list[CacheAdviceEntry] = Field(default_factory=list)


class BufferPoolReport(BaseModel):
    """Consolidated buffer pool statistics report.

    Attributes:
        pools: Sizing and performance metrics per buffer pool.
        free_buffer_inspected_total: Total free buffers inspected across instance.
        dirty_buffers_inspected_total: Total dirty buffers inspected across instance.
    """

    model_config = {"extra": "forbid"}

    pools: list[BufferPoolStat] = Field(default_factory=list)
    free_buffer_inspected_total: int = 0
    dirty_buffers_inspected_total: int = 0


class CpuTimeModelMetric(BaseModel):
    """System time model metric from V$SYS_TIME_MODEL.

    Attributes:
        stat_name: Metric name from time model.
        time_seconds: Accumulated time in seconds.
        pct_of_db_time: Percentage of total DB Time represented by this metric.
    """

    model_config = {"extra": "forbid"}

    stat_name: str
    time_seconds: float
    pct_of_db_time: float | None = None


class OsStatMetric(BaseModel):
    """Operating system statistic from V$OSSTAT.

    Attributes:
        stat_name: OS statistic identifier.
        value: Numeric statistic value.
        comments: Description or comments from Oracle view.
    """

    model_config = {"extra": "forbid"}

    stat_name: str
    value: float
    comments: str | None = None


class CpuUsageReport(BaseModel):
    """CPU usage and time model diagnostic report.

    Attributes:
        db_cpu_seconds: Total database CPU consumption time in seconds.
        background_cpu_seconds: Background process CPU consumption time in seconds.
        parse_time_cpu_seconds: CPU time spent parsing SQL statements in seconds.
        sql_execute_cpu_seconds: CPU time spent executing SQL statements in seconds.
        db_time_seconds: Total DB Time accumulated across all active sessions.
        total_os_cpu_seconds: Total OS busy CPU time in seconds.
        host_cpu_count: Number of CPU cores or threads available on the host.
        host_load: Host OS average load.
        cpu_time_pct_of_db_time: Percentage of DB Time spent on CPU.
        wait_time_pct_of_db_time: Percentage of DB Time spent on wait events.
        time_model_metrics: Detailed time model breakdown from V$SYS_TIME_MODEL.
        os_stats: Host operating system statistics from V$OSSTAT.
    """

    model_config = {"extra": "forbid"}

    db_cpu_seconds: float = 0.0
    background_cpu_seconds: float = 0.0
    parse_time_cpu_seconds: float = 0.0
    sql_execute_cpu_seconds: float = 0.0
    db_time_seconds: float = 0.0
    total_os_cpu_seconds: float | None = None
    host_cpu_count: int | None = None
    host_load: float | None = None
    cpu_time_pct_of_db_time: float = 0.0
    wait_time_pct_of_db_time: float = 0.0
    time_model_metrics: list[CpuTimeModelMetric] = Field(default_factory=list)
    os_stats: list[OsStatMetric] = Field(default_factory=list)


class FileIoStat(BaseModel):
    """Per-file I/O performance and latency statistics.

    Attributes:
        tablespace_name: Tablespace containing the file.
        file_id: File number.
        file_name: Physical file path or name.
        file_type: Type of file (DATA or TEMP).
        physical_reads: Number of physical data block reads.
        physical_writes: Number of physical data block writes.
        read_time_ms: Total time spent reading data blocks in milliseconds.
        write_time_ms: Total time spent writing data blocks in milliseconds.
        avg_read_latency_ms: Average read latency in milliseconds per read.
        avg_write_latency_ms: Average write latency in milliseconds per write.
    """

    model_config = {"extra": "forbid"}

    tablespace_name: str
    file_id: int | None = None
    file_name: str
    file_type: str = "DATA"
    physical_reads: int
    physical_writes: int
    read_time_ms: float
    write_time_ms: float
    avg_read_latency_ms: float
    avg_write_latency_ms: float


class TablespaceIoSummary(BaseModel):
    """Aggregated I/O metrics by tablespace.

    Attributes:
        tablespace_name: Tablespace name.
        physical_reads: Total physical reads across tablespace files.
        physical_writes: Total physical writes across tablespace files.
        read_time_ms: Total read time in milliseconds.
        write_time_ms: Total write time in milliseconds.
        avg_read_latency_ms: Weighted average read latency in milliseconds.
        avg_write_latency_ms: Weighted average write latency in milliseconds.
    """

    model_config = {"extra": "forbid"}

    tablespace_name: str
    physical_reads: int
    physical_writes: int
    read_time_ms: float
    write_time_ms: float
    avg_read_latency_ms: float
    avg_write_latency_ms: float


class IoFunctionStat(BaseModel):
    """I/O statistics by database function from V$IOSTAT_FUNCTION.

    Attributes:
        function_name: Database functional component (e.g. RMAN, DBWR, LGWR).
        physical_reads: Total read requests.
        physical_writes: Total write requests.
        read_time_ms: Total read service time in milliseconds.
        write_time_ms: Total write service time in milliseconds.
    """

    model_config = {"extra": "forbid"}

    function_name: str
    physical_reads: int
    physical_writes: int
    read_time_ms: float
    write_time_ms: float


class IoStatReport(BaseModel):
    """Consolidated database I/O performance report.

    Attributes:
        file_stats: Detailed I/O metrics per data and temp file.
        tablespace_summaries: Aggregated I/O metrics per tablespace.
        iostat_functions: Functional breakdown from V$IOSTAT_FUNCTION.
        source_view: Data source view used for metrics collection.
    """

    model_config = {"extra": "forbid"}

    file_stats: list[FileIoStat] = Field(default_factory=list)
    tablespace_summaries: list[TablespaceIoSummary] = Field(default_factory=list)
    iostat_functions: list[IoFunctionStat] = Field(default_factory=list)
    source_view: str = "V$FILESTAT"


class LatchStatMetric(BaseModel):
    """Latch acquisition, contention, and wait statistics from V$LATCH.

    Attributes:
        name: Name of the latch.
        gets: Number of willing-to-wait get requests.
        immediate_gets: Number of immediate get requests.
        misses: Number of times willing-to-wait get failed on first attempt.
        spin_gets: Number of gets obtained after spinning.
        sleeps: Number of times willing-to-wait sleep occurred.
        wait_time_ms: Total time waited for latch in milliseconds.
        hit_ratio_pct: Latch hit ratio percentage ((gets - misses) / gets * 100).
        sleep_rate_pct: Sleep rate percentage when missed (sleeps / misses * 100).
    """

    model_config = {"extra": "forbid"}

    name: str
    gets: int
    immediate_gets: int
    misses: int
    spin_gets: int
    sleeps: int
    wait_time_ms: float
    hit_ratio_pct: float
    sleep_rate_pct: float


class LatchMissDetail(BaseModel):
    """Latch miss location breakdown from V$LATCH_MISSES.

    Attributes:
        parent_name: Name of latch with misses.
        where_in_code: Internal Oracle code location identifier.
        nwfail_count: Number of no-wait acquisition failures.
        sleep_count: Number of times sleeping at this code location.
        wtr_slp_count: Number of times waiter slept.
    """

    model_config = {"extra": "forbid"}

    parent_name: str
    where_in_code: str
    nwfail_count: int
    sleep_count: int
    wtr_slp_count: int


class LatchStatsReport(BaseModel):
    """Consolidated latch contention and miss diagnostics report.

    Attributes:
        latches: Top latches ranked by sleeps and wait time.
        latch_misses: Internal code miss details from V$LATCH_MISSES.
    """

    model_config = {"extra": "forbid"}

    latches: list[LatchStatMetric] = Field(default_factory=list)
    latch_misses: list[LatchMissDetail] = Field(default_factory=list)


class SystemParseMetrics(BaseModel):
    """System-wide SQL parse statistics from V$SYSSTAT.

    Attributes:
        parse_count_total: Total SQL statements parsed (soft + hard).
        parse_count_hard: Total hard parses executed.
        parse_count_failures: Total failed parse attempts.
        parse_time_cpu_seconds: Total CPU time spent parsing statements.
        session_cursor_cache_hits: Total hits against session cursor cache.
        hard_parse_pct: Percentage of parses that required a hard parse.
        cursor_cache_hit_pct: Percentage of total parses hitting cursor cache.
    """

    model_config = {"extra": "forbid"}

    parse_count_total: int
    parse_count_hard: int
    parse_count_failures: int
    parse_time_cpu_seconds: float
    session_cursor_cache_hits: int
    hard_parse_pct: float
    cursor_cache_hit_pct: float


class HighParseSqlDetail(BaseModel):
    """Diagnostics for a SQL statement exhibiting high parse frequency.

    Attributes:
        sql_id: SQL statement identifier.
        parse_calls: Number of parse requests for this statement.
        executions: Number of executions for this statement.
        parse_per_exec_ratio: Ratio of parse calls per execution.
        version_count: Number of child cursor versions generated.
        invalidations: Number of times cursor was invalidated.
        cpu_time_ms: Accumulated CPU execution time in milliseconds.
        elapsed_time_ms: Accumulated elapsed execution time in milliseconds.
        module: Application module name executing the SQL.
        sql_text: SQL text snippet.
        diagnoses: Root-cause diagnosis findings and tuning advice.
    """

    model_config = {"extra": "forbid"}

    sql_id: str
    parse_calls: int
    executions: int
    parse_per_exec_ratio: float
    version_count: int
    invalidations: int
    cpu_time_ms: float
    elapsed_time_ms: float
    module: str | None = None
    sql_text: str
    diagnoses: list[str] = Field(default_factory=list)


class HighParseSqlReport(BaseModel):
    """Consolidated SQL parse diagnostics report.

    Attributes:
        system_parse_metrics: System-wide parse metrics from V$SYSSTAT.
        offending_sql: SQL statements with high parse rates.
        overall_recommendations: High-level tuning recommendations.
    """

    model_config = {"extra": "forbid"}

    system_parse_metrics: SystemParseMetrics | None = None
    offending_sql: list[HighParseSqlDetail] = Field(default_factory=list)
    overall_recommendations: list[str] = Field(default_factory=list)


class SystemMetricsDiagnosticsReport(BaseModel):
    """Consolidated system metrics and SQL parse diagnostics report.

    Attributes:
        timestamp: Analysis execution timestamp.
        buffer_pool: Buffer pool sizing and cache advice metrics.
        cpu_usage: CPU utilization and time model breakdown.
        io_stats: I/O throughput and latency metrics.
        latch_stats: Latch contention and miss statistics.
        high_parse_sql: High parse rate queries and root-cause diagnoses.
    """

    model_config = {"extra": "forbid"}

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    buffer_pool: BufferPoolReport | None = None
    cpu_usage: CpuUsageReport | None = None
    io_stats: IoStatReport | None = None
    latch_stats: LatchStatsReport | None = None
    high_parse_sql: HighParseSqlReport | None = None


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
        """Open and yield an Oracle database connection in Thin mode.

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
            sysdba=self._config.is_sysdba,
        ).debug("Opening Oracle session")

        connection = None
        try:
            connection = oracledb.connect(
                user=self._config.username,
                password=password,
                dsn=dsn,
                mode=mode,
            )
            yield connection
        except oracledb.DatabaseError as exc:
            logger.bind(
                host=self._config.hostname,
                user=self._config.username,
            ).error("Oracle connection failure: {}", exc)
            raise
        finally:
            if connection is not None:
                try:
                    connection.close()
                except oracledb.DatabaseError as exc:
                    logger.warning("Error closing Oracle connection: {}", exc)


class OracleSystemMetricsAnalyzer:
    """Performs Oracle system metrics and SQL parse diagnostics analysis."""

    def __init__(
        self,
        driver: OracleDriver,
        top_n: int = 20,
        min_parses: int = 100,
    ) -> None:
        """Initialize analyzer with driver and analysis thresholds.

        Args:
            driver (OracleDriver): Database driver providing session management.
            top_n (int): Maximum number of rows to return for ranked metrics.
            min_parses (int): Minimum parse count threshold for offending SQL queries.
        """
        self._driver = driver
        self._top_n = top_n
        self._min_parses = min_parses

    def analyze_buffer_pool(self) -> BufferPoolReport:
        """Query V$BUFFER_POOL_STATISTICS, V$DB_CACHE_ADVICE, and V$SYSSTAT.

        Returns:
            BufferPoolReport: Buffer pool metrics with cache advice projections.
        """
        report = BufferPoolReport()

        # 1. Query sysstat for inspected buffers
        sysstat_sql = """
            SELECT name, value
            FROM v$sysstat
            WHERE name IN ('free buffer inspected', 'dirty buffers inspected')
        """
        try:
            with self._driver.session() as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(sysstat_sql)
                    sys_rows = cursor.fetchall()
                except oracledb.DatabaseError as exc:
                    logger.error("Failed to query V$SYSSTAT for buffer inspection: {}", exc)
                    raise

                for row in sys_rows:
                    stat_name = str(row[0]).strip().lower()
                    val = int(row[1] or 0)
                    if stat_name == "free buffer inspected":
                        report.free_buffer_inspected_total = val
                    elif stat_name == "dirty buffers inspected":
                        report.dirty_buffers_inspected_total = val
        except oracledb.DatabaseError as exc:
            if "ORA-00942" in str(exc):
                logger.warning("V$SYSSTAT view not accessible: {}", exc)
            else:
                raise

        # 2. Query buffer pool statistics
        pool_sql = """
            SELECT
                COALESCE(name, 'DEFAULT') AS pool_name,
                COALESCE(block_size, 8192) AS block_size,
                ROUND(COALESCE(buffers, 0) * COALESCE(block_size, 8192) / (1024 * 1024), 2) AS size_mb,
                COALESCE(physical_reads, 0) AS physical_reads,
                COALESCE(physical_writes, 0) AS physical_writes,
                COALESCE(db_block_gets, 0) AS db_block_gets,
                COALESCE(consistent_gets, 0) AS consistent_gets,
                CASE
                    WHEN (COALESCE(db_block_gets, 0) + COALESCE(consistent_gets, 0)) > 0
                    THEN ROUND((1 - (COALESCE(physical_reads, 0) / (COALESCE(db_block_gets, 0) + COALESCE(consistent_gets, 0)))) * 100, 2)
                    ELSE 100.0
                END AS hit_ratio_pct
            FROM v$buffer_pool_statistics
            ORDER BY pool_name
        """
        pool_stats: dict[str, BufferPoolStat] = {}
        try:
            with self._driver.session() as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(pool_sql)
                    pool_rows = cursor.fetchall()
                except oracledb.DatabaseError as exc:
                    logger.error("Failed to query V$BUFFER_POOL_STATISTICS: {}", exc)
                    raise

                for row in pool_rows:
                    p_name = str(row[0])
                    pool_stat = BufferPoolStat(
                        pool_name=p_name,
                        block_size_bytes=int(row[1] or 8192),
                        size_mb=float(row[2] or 0.0),
                        physical_reads=int(row[3] or 0),
                        physical_writes=int(row[4] or 0),
                        db_block_gets=int(row[5] or 0),
                        consistent_gets=int(row[6] or 0),
                        cache_hit_ratio_pct=float(row[7] or 100.0),
                        free_buffer_inspected=report.free_buffer_inspected_total,
                        dirty_buffers_inspected=report.dirty_buffers_inspected_total,
                    )
                    pool_stats[p_name.upper()] = pool_stat
        except oracledb.DatabaseError as exc:
            if "ORA-00942" in str(exc):
                logger.warning("V$BUFFER_POOL_STATISTICS view not accessible: {}", exc)
            else:
                raise

        # 3. Query cache advice
        advice_sql = """
            SELECT
                name AS pool_name,
                block_size,
                size_factor,
                size_for_estimate AS size_mb,
                estd_physical_reads,
                estd_physical_read_factor,
                ROUND(COALESCE(estd_physical_read_time, 0) * 10, 2) AS estd_physical_read_time_ms
            FROM v$db_cache_advice
            ORDER BY pool_name, size_factor
        """
        try:
            with self._driver.session() as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(advice_sql)
                    advice_rows = cursor.fetchall()
                except oracledb.DatabaseError as exc:
                    logger.error("Failed to query V$DB_CACHE_ADVICE: {}", exc)
                    raise

                for row in advice_rows:
                    p_name = str(row[0])
                    entry = CacheAdviceEntry(
                        pool_name=p_name,
                        block_size_bytes=int(row[1] or 8192),
                        size_factor=float(row[2] or 1.0),
                        size_mb=float(row[3] or 0.0),
                        estd_physical_reads=int(row[4] or 0),
                        estd_physical_read_factor=float(row[5] or 1.0),
                        estd_physical_read_time_ms=float(row[6] or 0.0),
                    )
                    key = p_name.upper()
                    if key in pool_stats:
                        pool_stats[key].cache_advice.append(entry)
                    else:
                        new_pool = BufferPoolStat(
                            pool_name=p_name,
                            block_size_bytes=entry.block_size_bytes,
                            size_mb=entry.size_mb if entry.size_factor == 1.0 else 0.0,
                            physical_reads=0,
                            physical_writes=0,
                            db_block_gets=0,
                            consistent_gets=0,
                            cache_hit_ratio_pct=100.0,
                            free_buffer_inspected=report.free_buffer_inspected_total,
                            dirty_buffers_inspected=report.dirty_buffers_inspected_total,
                            cache_advice=[entry],
                        )
                        pool_stats[key] = new_pool
        except oracledb.DatabaseError as exc:
            if "ORA-00942" in str(exc):
                logger.warning("V$DB_CACHE_ADVICE view not accessible: {}", exc)
            else:
                raise

        report.pools = list(pool_stats.values())
        return report

    def analyze_cpu_usage(self) -> CpuUsageReport:
        """Query V$SYS_TIME_MODEL and V$OSSTAT for CPU and wait metrics.

        Returns:
            CpuUsageReport: CPU consumption, host metrics, and DB Time distribution.
        """
        report = CpuUsageReport()

        # 1. Query V$SYS_TIME_MODEL
        time_model_sql = """
            SELECT stat_name, ROUND(value / 1000000, 4) AS time_seconds
            FROM v$sys_time_model
            WHERE value > 0
            ORDER BY value DESC
        """
        raw_time_model: dict[str, float] = {}
        try:
            with self._driver.session() as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(time_model_sql)
                    rows = cursor.fetchall()
                except oracledb.DatabaseError as exc:
                    logger.error("Failed to query V$SYS_TIME_MODEL: {}", exc)
                    raise

                for row in rows:
                    name = str(row[0])
                    sec = float(row[1] or 0.0)
                    raw_time_model[name] = sec
        except oracledb.DatabaseError as exc:
            if "ORA-00942" in str(exc):
                logger.warning("V$SYS_TIME_MODEL view not accessible: {}", exc)
            else:
                raise

        db_time = raw_time_model.get("DB time", 0.0)
        db_cpu = raw_time_model.get("DB CPU", 0.0)
        bg_cpu = raw_time_model.get("background cpu time", 0.0)
        parse_cpu = raw_time_model.get("parse time cpu", 0.0)
        sql_exec_cpu = raw_time_model.get("sql execute elapsed time", 0.0)

        report.db_time_seconds = round(db_time, 4)
        report.db_cpu_seconds = round(db_cpu, 4)
        report.background_cpu_seconds = round(bg_cpu, 4)
        report.parse_time_cpu_seconds = round(parse_cpu, 4)
        report.sql_execute_cpu_seconds = round(sql_exec_cpu, 4)

        if db_time > 0.0:
            cpu_pct = min(100.0, round((db_cpu / db_time) * 100, 2))
            wait_pct = max(0.0, round(100.0 - cpu_pct, 2))
            report.cpu_time_pct_of_db_time = cpu_pct
            report.wait_time_pct_of_db_time = wait_pct

        for name, sec in raw_time_model.items():
            pct = round((sec / db_time) * 100, 2) if db_time > 0.0 else None
            report.time_model_metrics.append(
                CpuTimeModelMetric(
                    stat_name=name,
                    time_seconds=sec,
                    pct_of_db_time=pct,
                )
            )

        # 2. Query V$OSSTAT
        osstat_sql = """
            SELECT stat_name, value, comments
            FROM v$osstat
        """
        try:
            with self._driver.session() as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(osstat_sql)
                    os_rows = cursor.fetchall()
                except oracledb.DatabaseError as exc:
                    logger.error("Failed to query V$OSSTAT: {}", exc)
                    raise

                busy_time_centi = 0.0
                has_busy = False

                for row in os_rows:
                    s_name = str(row[0])
                    s_val = float(row[1] or 0.0)
                    s_comm = str(row[2]) if row[2] is not None else None

                    report.os_stats.append(OsStatMetric(stat_name=s_name, value=s_val, comments=s_comm))

                    if s_name in ("NUM_CPUS", "NUM_CPU_CORES") and report.host_cpu_count is None:
                        report.host_cpu_count = int(s_val)
                    elif s_name == "LOAD":
                        report.host_load = round(s_val, 2)
                    elif s_name == "BUSY_TIME":
                        busy_time_centi = s_val
                        has_busy = True
                    elif s_name in ("USER_TIME", "SYS_TIME") and not has_busy:
                        busy_time_centi += s_val

                if busy_time_centi > 0.0:
                    report.total_os_cpu_seconds = round(busy_time_centi / 100.0, 2)
        except oracledb.DatabaseError as exc:
            if "ORA-00942" in str(exc):
                logger.warning("V$OSSTAT view not accessible: {}", exc)
            else:
                raise

        return report

    def analyze_io_stats(self) -> IoStatReport:
        """Query V$FILESTAT and DBA/V$ views with fallback to V$IOSTAT.

        Returns:
            IoStatReport: File and tablespace I/O breakdown and latencies.
        """
        report = IoStatReport()

        # Primary query using V$FILESTAT and V$DATAFILE / V$TEMPFILE
        filestat_sql = """
            SELECT * FROM (
                SELECT
                    ts.name AS tablespace_name,
                    f.file# AS file_id,
                    df.name AS file_name,
                    'DATA' AS file_type,
                    f.phyrds AS physical_reads,
                    f.phywrts AS physical_writes,
                    ROUND(f.readtim * 10, 2) AS read_time_ms,
                    ROUND(f.writetim * 10, 2) AS write_time_ms,
                    CASE
                        WHEN f.phyrds > 0 THEN ROUND((f.readtim * 10) / f.phyrds, 2)
                        ELSE 0.0
                    END AS avg_read_latency_ms,
                    CASE
                        WHEN f.phywrts > 0 THEN ROUND((f.writetim * 10) / f.phywrts, 2)
                        ELSE 0.0
                    END AS avg_write_latency_ms
                FROM v$filestat f
                JOIN v$datafile df ON f.file# = df.file#
                JOIN v$tablespace ts ON df.ts# = ts.ts#
                UNION ALL
                SELECT
                    ts.name AS tablespace_name,
                    tf.file# AS file_id,
                    tf.name AS file_name,
                    'TEMP' AS file_type,
                    t.phyrds AS physical_reads,
                    t.phywrts AS physical_writes,
                    ROUND(t.readtim * 10, 2) AS read_time_ms,
                    ROUND(t.writetim * 10, 2) AS write_time_ms,
                    CASE
                        WHEN t.phyrds > 0 THEN ROUND((t.readtim * 10) / t.phyrds, 2)
                        ELSE 0.0
                    END AS avg_read_latency_ms,
                    CASE
                        WHEN t.phywrts > 0 THEN ROUND((t.writetim * 10) / t.phywrts, 2)
                        ELSE 0.0
                    END AS avg_write_latency_ms
                FROM v$tempstat t
                JOIN v$tempfile tf ON t.file# = tf.file#
                JOIN v$tablespace ts ON tf.ts# = ts.ts#
                ORDER BY (physical_reads + physical_writes) DESC
            )
            WHERE ROWNUM <= :top_n
        """
        try:
            with self._driver.session() as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(filestat_sql, {"top_n": self._top_n})
                    rows = cursor.fetchall()
                except oracledb.DatabaseError as exc:
                    logger.warning("V$FILESTAT query failed: {}, attempting fallback", exc)
                    raise

                for row in rows:
                    report.file_stats.append(
                        FileIoStat(
                            tablespace_name=str(row[0]),
                            file_id=int(row[1]) if row[1] is not None else None,
                            file_name=str(row[2]),
                            file_type=str(row[3]),
                            physical_reads=int(row[4] or 0),
                            physical_writes=int(row[5] or 0),
                            read_time_ms=float(row[6] or 0.0),
                            write_time_ms=float(row[7] or 0.0),
                            avg_read_latency_ms=float(row[8] or 0.0),
                            avg_write_latency_ms=float(row[9] or 0.0),
                        )
                    )
                report.source_view = "V$FILESTAT"
        except oracledb.DatabaseError as exc:
            if "ORA-00942" in str(exc) or "not accessible" in str(exc):
                # Fallback to V$IOSTAT_FILE
                logger.info("Falling back to V$IOSTAT_FILE for I/O diagnostics")
                fallback_sql = """
                    SELECT * FROM (
                        SELECT
                            'UNKNOWN' AS tablespace_name,
                            file_no AS file_id,
                            COALESCE(file_name, 'file#' || file_no) AS file_name,
                            COALESCE(file_type, 'DATA') AS file_type,
                            COALESCE(small_read_reqs, 0) + COALESCE(large_read_reqs, 0) AS physical_reads,
                            COALESCE(small_write_reqs, 0) + COALESCE(large_write_reqs, 0) AS physical_writes,
                            ROUND(COALESCE(small_read_servicetime, 0) + COALESCE(large_read_servicetime, 0), 2) AS read_time_ms,
                            ROUND(COALESCE(small_write_servicetime, 0) + COALESCE(large_write_servicetime, 0), 2) AS write_time_ms,
                            CASE
                                WHEN (COALESCE(small_read_reqs, 0) + COALESCE(large_read_reqs, 0)) > 0
                                THEN ROUND((COALESCE(small_read_servicetime, 0) + COALESCE(large_read_servicetime, 0)) / (COALESCE(small_read_reqs, 0) + COALESCE(large_read_reqs, 0)), 2)
                                ELSE 0.0
                            END AS avg_read_latency_ms,
                            CASE
                                WHEN (COALESCE(small_write_reqs, 0) + COALESCE(large_write_reqs, 0)) > 0
                                THEN ROUND((COALESCE(small_write_servicetime, 0) + COALESCE(large_write_servicetime, 0)) / (COALESCE(small_write_reqs, 0) + COALESCE(large_write_reqs, 0)), 2)
                                ELSE 0.0
                            END AS avg_write_latency_ms
                        FROM v$iostat_file
                        ORDER BY (physical_reads + physical_writes) DESC
                    )
                    WHERE ROWNUM <= :top_n
                """
                try:
                    with self._driver.session() as conn, conn.cursor() as cursor:
                        try:
                            cursor.execute(fallback_sql, {"top_n": self._top_n})
                            fb_rows = cursor.fetchall()
                        except oracledb.DatabaseError as fb_exc:
                            logger.error("Failed to query V$IOSTAT_FILE: {}", fb_exc)
                            raise

                        for row in fb_rows:
                            report.file_stats.append(
                                FileIoStat(
                                    tablespace_name=str(row[0]),
                                    file_id=int(row[1]) if row[1] is not None else None,
                                    file_name=str(row[2]),
                                    file_type=str(row[3]),
                                    physical_reads=int(row[4] or 0),
                                    physical_writes=int(row[5] or 0),
                                    read_time_ms=float(row[6] or 0.0),
                                    write_time_ms=float(row[7] or 0.0),
                                    avg_read_latency_ms=float(row[8] or 0.0),
                                    avg_write_latency_ms=float(row[9] or 0.0),
                                )
                            )
                        report.source_view = "V$IOSTAT_FILE"
                except oracledb.DatabaseError as fb_exc:
                    if "ORA-00942" in str(fb_exc):
                        logger.warning("V$IOSTAT_FILE view not accessible: {}", fb_exc)
                    else:
                        raise
            else:
                raise

        # Aggregate tablespace summaries from file_stats
        ts_map: dict[str, dict[str, float]] = {}
        for f in report.file_stats:
            ts_name = f.tablespace_name
            if ts_name not in ts_map:
                ts_map[ts_name] = {
                    "reads": 0.0,
                    "writes": 0.0,
                    "read_time": 0.0,
                    "write_time": 0.0,
                }
            ts_map[ts_name]["reads"] += f.physical_reads
            ts_map[ts_name]["writes"] += f.physical_writes
            ts_map[ts_name]["read_time"] += f.read_time_ms
            ts_map[ts_name]["write_time"] += f.write_time_ms

        for ts_name, data in sorted(
            ts_map.items(),
            key=lambda item: item[1]["reads"] + item[1]["writes"],
            reverse=True,
        ):
            reads = int(data["reads"])
            writes = int(data["writes"])
            read_time = round(data["read_time"], 2)
            write_time = round(data["write_time"], 2)
            avg_r_lat = round(read_time / reads, 2) if reads > 0 else 0.0
            avg_w_lat = round(write_time / writes, 2) if writes > 0 else 0.0

            report.tablespace_summaries.append(
                TablespaceIoSummary(
                    tablespace_name=ts_name,
                    physical_reads=reads,
                    physical_writes=writes,
                    read_time_ms=read_time,
                    write_time_ms=write_time,
                    avg_read_latency_ms=avg_r_lat,
                    avg_write_latency_ms=avg_w_lat,
                )
            )

        # Query V$IOSTAT_FUNCTION for functional breakdown
        func_sql = """
            SELECT * FROM (
                SELECT
                    function_name,
                    COALESCE(small_read_reqs, 0) + COALESCE(large_read_reqs, 0) AS physical_reads,
                    COALESCE(small_write_reqs, 0) + COALESCE(large_write_reqs, 0) AS physical_writes,
                    ROUND(COALESCE(small_read_servicetime, 0) + COALESCE(large_read_servicetime, 0), 2) AS read_time_ms,
                    ROUND(COALESCE(small_write_servicetime, 0) + COALESCE(large_write_servicetime, 0), 2) AS write_time_ms
                FROM v$iostat_function
                ORDER BY (physical_reads + physical_writes) DESC
            )
            WHERE ROWNUM <= :top_n
        """
        try:
            with self._driver.session() as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(func_sql, {"top_n": self._top_n})
                    func_rows = cursor.fetchall()
                except oracledb.DatabaseError as exc:
                    logger.error("Failed to query V$IOSTAT_FUNCTION: {}", exc)
                    raise

                for row in func_rows:
                    report.iostat_functions.append(
                        IoFunctionStat(
                            function_name=str(row[0]),
                            physical_reads=int(row[1] or 0),
                            physical_writes=int(row[2] or 0),
                            read_time_ms=float(row[3] or 0.0),
                            write_time_ms=float(row[4] or 0.0),
                        )
                    )
        except oracledb.DatabaseError as exc:
            if "ORA-00942" in str(exc):
                logger.warning("V$IOSTAT_FUNCTION view not accessible: {}", exc)
            else:
                raise

        return report

    def analyze_latch_stats(self) -> LatchStatsReport:
        """Query V$LATCH and V$LATCH_MISSES for latch contention and sleep rates.

        Returns:
            LatchStatsReport: Ranked latches and miss locations.
        """
        report = LatchStatsReport()

        # 1. Query V$LATCH
        latch_sql = """
            SELECT * FROM (
                SELECT
                    name,
                    gets,
                    immediate_gets,
                    misses,
                    spin_gets,
                    sleeps,
                    ROUND(wait_time / 1000, 2) AS wait_time_ms,
                    CASE
                        WHEN gets > 0 THEN ROUND(((gets - misses) / gets) * 100, 2)
                        ELSE 100.0
                    END AS hit_ratio_pct,
                    CASE
                        WHEN misses > 0 THEN ROUND((sleeps / misses) * 100, 2)
                        ELSE 0.0
                    END AS sleep_rate_pct
                FROM v$latch
                WHERE gets > 0 OR misses > 0 OR sleeps > 0 OR immediate_gets > 0
                ORDER BY sleeps DESC, wait_time DESC
            )
            WHERE ROWNUM <= :top_n
        """
        try:
            with self._driver.session() as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(latch_sql, {"top_n": self._top_n})
                    latch_rows = cursor.fetchall()
                except oracledb.DatabaseError as exc:
                    logger.error("Failed to query V$LATCH: {}", exc)
                    raise

                for row in latch_rows:
                    report.latches.append(
                        LatchStatMetric(
                            name=str(row[0]),
                            gets=int(row[1] or 0),
                            immediate_gets=int(row[2] or 0),
                            misses=int(row[3] or 0),
                            spin_gets=int(row[4] or 0),
                            sleeps=int(row[5] or 0),
                            wait_time_ms=float(row[6] or 0.0),
                            hit_ratio_pct=float(row[7] or 100.0),
                            sleep_rate_pct=float(row[8] or 0.0),
                        )
                    )
        except oracledb.DatabaseError as exc:
            if "ORA-00942" in str(exc):
                logger.warning("V$LATCH view not accessible: {}", exc)
            else:
                raise

        # 2. Query V$LATCH_MISSES
        misses_sql = """
            SELECT * FROM (
                SELECT
                    parent_name,
                    "WHERE" AS where_in_code,
                    COALESCE(nwfail_count, 0) AS nwfail_count,
                    COALESCE(sleep_count, 0) AS sleep_count,
                    COALESCE(wtr_slp_count, 0) AS wtr_slp_count
                FROM v$latch_misses
                WHERE sleep_count > 0 OR nwfail_count > 0
                ORDER BY sleep_count DESC
            )
            WHERE ROWNUM <= :top_n
        """
        try:
            with self._driver.session() as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(misses_sql, {"top_n": self._top_n})
                    miss_rows = cursor.fetchall()
                except oracledb.DatabaseError as exc:
                    logger.error("Failed to query V$LATCH_MISSES: {}", exc)
                    raise

                for row in miss_rows:
                    report.latch_misses.append(
                        LatchMissDetail(
                            parent_name=str(row[0]),
                            where_in_code=str(row[1]),
                            nwfail_count=int(row[2] or 0),
                            sleep_count=int(row[3] or 0),
                            wtr_slp_count=int(row[4] or 0),
                        )
                    )
        except oracledb.DatabaseError as exc:
            if "ORA-00942" in str(exc):
                logger.warning("V$LATCH_MISSES view not accessible: {}", exc)
            else:
                raise

        return report

    def analyze_high_parse_sql(self) -> HighParseSqlReport:
        """Query system parse statistics and offending SQL queries.

        Returns:
            HighParseSqlReport: System parse metrics, offending SQL, and root-cause diagnoses.
        """
        report = HighParseSqlReport()

        # 1. System parse metrics from V$SYSSTAT
        sysstat_sql = """
            SELECT name, value
            FROM v$sysstat
            WHERE name IN (
                'parse count (total)',
                'parse count (hard)',
                'parse count (failures)',
                'parse time cpu',
                'session cursor cache hits'
            )
        """
        raw_sysstat: dict[str, int] = {}
        try:
            with self._driver.session() as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(sysstat_sql)
                    rows = cursor.fetchall()
                except oracledb.DatabaseError as exc:
                    logger.error("Failed to query V$SYSSTAT for parse metrics: {}", exc)
                    raise

                for row in rows:
                    name = str(row[0]).strip().lower()
                    raw_sysstat[name] = int(row[1] or 0)
        except oracledb.DatabaseError as exc:
            if "ORA-00942" in str(exc):
                logger.warning("V$SYSSTAT view not accessible: {}", exc)
            else:
                raise

        total_parses = raw_sysstat.get("parse count (total)", 0)
        hard_parses = raw_sysstat.get("parse count (hard)", 0)
        failed_parses = raw_sysstat.get("parse count (failures)", 0)
        parse_cpu_centisec = raw_sysstat.get("parse time cpu", 0)
        cursor_hits = raw_sysstat.get("session cursor cache hits", 0)

        hard_pct = round((hard_parses / total_parses) * 100, 2) if total_parses > 0 else 0.0
        cache_hit_pct = round((cursor_hits / total_parses) * 100, 2) if total_parses > 0 else 0.0

        if raw_sysstat:
            report.system_parse_metrics = SystemParseMetrics(
                parse_count_total=total_parses,
                parse_count_hard=hard_parses,
                parse_count_failures=failed_parses,
                parse_time_cpu_seconds=round(parse_cpu_centisec / 100.0, 2),
                session_cursor_cache_hits=cursor_hits,
                hard_parse_pct=hard_pct,
                cursor_cache_hit_pct=cache_hit_pct,
            )

            # System-wide recommendations
            if hard_pct > 20.0:
                report.overall_recommendations.append(f"High hard parse percentage ({hard_pct:.1f}%): Applications may be concatenating literals into SQL strings rather than using bind variables. Use bind variables or consider CURSOR_SHARING=FORCE as a temporary mitigation.")
            if cache_hit_pct < 50.0 and total_parses > 100:
                report.overall_recommendations.append(f"Low session cursor cache hit ratio ({cache_hit_pct:.1f}%): Consider increasing SESSION_CACHED_CURSORS parameter (e.g. to 100-300) to improve cursor reuse across loops and repeated calls.")
            if failed_parses > 0:
                report.overall_recommendations.append(f"Detected {failed_parses} parse failures: Check application logs for SQL syntax errors, permission issues, or queries referencing missing objects.")

        # 2. Query offending SQL with high parse calls (try V$SQLSTATS first, fallback to V$SQL)
        sqlstats_query = """
            SELECT * FROM (
                SELECT
                    sql_id,
                    parse_calls,
                    executions,
                    CASE
                        WHEN executions > 0 THEN ROUND(parse_calls / executions, 2)
                        ELSE ROUND(parse_calls, 2)
                    END AS parse_per_exec_ratio,
                    version_count,
                    invalidations,
                    ROUND(cpu_time / 1000, 2) AS cpu_time_ms,
                    ROUND(elapsed_time / 1000, 2) AS elapsed_time_ms,
                    module,
                    SUBSTR(sql_text, 1, 300) AS sql_text
                FROM v$sqlstats
                WHERE parse_calls >= :min_parses
                ORDER BY parse_calls DESC
            )
            WHERE ROWNUM <= :top_n
        """
        sql_rows = []
        try:
            with self._driver.session() as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(
                        sqlstats_query,
                        {"min_parses": self._min_parses, "top_n": self._top_n},
                    )
                    sql_rows = cursor.fetchall()
                except oracledb.DatabaseError as exc:
                    logger.warning("V$SQLSTATS query failed: {}, attempting V$SQL", exc)
                    raise
        except oracledb.DatabaseError as exc:
            if "ORA-00942" in str(exc) or "not accessible" in str(exc):
                # Fallback to V$SQL
                vsql_query = """
                    SELECT * FROM (
                        SELECT
                            sql_id,
                            SUM(parse_calls) AS parse_calls,
                            SUM(executions) AS executions,
                            CASE
                                WHEN SUM(executions) > 0 THEN ROUND(SUM(parse_calls) / SUM(executions), 2)
                                ELSE ROUND(SUM(parse_calls), 2)
                            END AS parse_per_exec_ratio,
                            MAX(version_count) AS version_count,
                            SUM(invalidations) AS invalidations,
                            ROUND(SUM(cpu_time) / 1000, 2) AS cpu_time_ms,
                            ROUND(SUM(elapsed_time) / 1000, 2) AS elapsed_time_ms,
                            MAX(module) AS module,
                            MAX(SUBSTR(sql_text, 1, 300)) AS sql_text
                        FROM v$sql
                        GROUP BY sql_id
                        HAVING SUM(parse_calls) >= :min_parses
                        ORDER BY SUM(parse_calls) DESC
                    )
                    WHERE ROWNUM <= :top_n
                """
                try:
                    with self._driver.session() as conn, conn.cursor() as cursor:
                        try:
                            cursor.execute(
                                vsql_query,
                                {"min_parses": self._min_parses, "top_n": self._top_n},
                            )
                            sql_rows = cursor.fetchall()
                        except oracledb.DatabaseError as vsql_exc:
                            logger.error("Failed to query V$SQL: {}", vsql_exc)
                            raise
                except oracledb.DatabaseError as vsql_exc:
                    if "ORA-00942" in str(vsql_exc):
                        logger.warning("V$SQL view not accessible: {}", vsql_exc)
                    else:
                        raise
            else:
                raise

        for row in sql_rows:
            sql_id = str(row[0])
            parse_calls = int(row[1] or 0)
            executions = int(row[2] or 0)
            parse_ratio = float(row[3] or 0.0)
            version_count = int(row[4] or 0)
            invalidations = int(row[5] or 0)
            cpu_time_ms = float(row[6] or 0.0)
            elapsed_time_ms = float(row[7] or 0.0)
            module = str(row[8]) if row[8] is not None else None
            sql_text = str(row[9] or "")

            diagnoses: list[str] = []
            if parse_ratio > 1.0:
                diagnoses.append(f"Excessive parse calls per execution (ratio {parse_ratio:.2f}): Statement is re-parsed on each execution. Enable statement caching in the application connection pool or hold open prepared statements.")
            if version_count > 50 or invalidations > 10:
                diagnoses.append(f"High child cursor versions ({version_count}) / invalidations ({invalidations}): Indicates cursor invalidation or bind metadata mismatch. Inspect V$SQL_SHARED_CURSOR to identify why cursors are not being shared.")
            if executions <= 1 and parse_calls >= self._min_parses:
                diagnoses.append("Potential unshared literal SQL: Statement was parsed multiple times with minimal reuse. Replace hardcoded literals with bind variables.")
            if not diagnoses:
                diagnoses.append("High parse volume statement. Review application cursor lifecycle.")

            report.offending_sql.append(
                HighParseSqlDetail(
                    sql_id=sql_id,
                    parse_calls=parse_calls,
                    executions=executions,
                    parse_per_exec_ratio=parse_ratio,
                    version_count=version_count,
                    invalidations=invalidations,
                    cpu_time_ms=cpu_time_ms,
                    elapsed_time_ms=elapsed_time_ms,
                    module=module,
                    sql_text=sql_text,
                    diagnoses=diagnoses,
                )
            )

        return report

    def run_all(self) -> SystemMetricsDiagnosticsReport:
        """Run all diagnostic analyzers and assemble a consolidated report.

        Returns:
            SystemMetricsDiagnosticsReport: Combined metrics from all analyzers.
        """
        logger.info("Executing comprehensive Oracle system metrics diagnostics")
        report = SystemMetricsDiagnosticsReport()
        report.buffer_pool = self.analyze_buffer_pool()
        report.cpu_usage = self.analyze_cpu_usage()
        report.io_stats = self.analyze_io_stats()
        report.latch_stats = self.analyze_latch_stats()
        report.high_parse_sql = self.analyze_high_parse_sql()
        return report


def format_system_metrics_report_text(report: SystemMetricsDiagnosticsReport) -> str:
    """Format consolidated metrics diagnostics report into human-readable text.

    Args:
        report (SystemMetricsDiagnosticsReport): Populated report model.

    Returns:
        str: Formatted multi-line text report.
    """
    lines: list[str] = []
    lines.append("=" * 80)
    lines.append("ORACLE SYSTEM METRICS & SQL PARSE DIAGNOSTICS REPORT")
    lines.append(f"Generated at: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("=" * 80)

    # 1. Buffer Pool Statistics
    if report.buffer_pool is not None:
        bp = report.buffer_pool
        lines.append("\n[1] BUFFER POOL STATISTICS & CACHE ADVICE")
        lines.append("-" * 80)
        lines.append(f"Total Free Buffers Inspected: {bp.free_buffer_inspected_total:,} | Total Dirty Buffers Inspected: {bp.dirty_buffers_inspected_total:,}")
        if bp.pools:
            lines.append(f"{'Pool Name':<12} {'Size MB':>10} {'Blk Size':>9} {'Phys Reads':>12} {'Phys Writes':>12} {'Block Gets':>12} {'Consist Gets':>12} {'Hit Ratio':>10}")
            lines.append("-" * 95)
            for p in bp.pools:
                lines.append(f"{p.pool_name:<12} {p.size_mb:>10.2f} {p.block_size_bytes:>9} {p.physical_reads:>12,d} {p.physical_writes:>12,d} {p.db_block_gets:>12,d} {p.consistent_gets:>12,d} {p.cache_hit_ratio_pct:>9.2f}%")
                if p.cache_advice:
                    lines.append("  Cache Sizing Advice Projections:")
                    lines.append(f"    {'Factor':>8} {'Size MB':>10} {'Estd Reads':>14} {'Read Factor':>12} {'Estd Time ms':>14}")
                    lines.append("    " + "-" * 62)
                    for adv in p.cache_advice:
                        lines.append(f"    {adv.size_factor:>8.2f} {adv.size_mb:>10.1f} {adv.estd_physical_reads:>14,d} {adv.estd_physical_read_factor:>12.4f} {adv.estd_physical_read_time_ms:>14.2f}")
        else:
            lines.append("  No buffer pool statistics available.")
    else:
        lines.append("\n[1] BUFFER POOL STATISTICS: Not requested or unavailable")

    # 2. CPU Usage Statistics
    if report.cpu_usage is not None:
        cpu = report.cpu_usage
        lines.append("\n[2] CPU USAGE & TIME MODEL STATISTICS")
        lines.append("-" * 80)
        lines.append(f"Host CPU Cores: {cpu.host_cpu_count or 'N/A'} | Host Load: {cpu.host_load if cpu.host_load is not None else 'N/A'} | Total OS CPU Time: {f'{cpu.total_os_cpu_seconds:.2f}s' if cpu.total_os_cpu_seconds is not None else 'N/A'}")
        lines.append(f"DB Time: {cpu.db_time_seconds:.2f}s | DB CPU Time: {cpu.db_cpu_seconds:.2f}s | Background CPU: {cpu.background_cpu_seconds:.2f}s | Parse CPU: {cpu.parse_time_cpu_seconds:.2f}s")
        lines.append(f"DB Time Distribution: CPU = {cpu.cpu_time_pct_of_db_time:.2f}% | Wait Events = {cpu.wait_time_pct_of_db_time:.2f}%")
        if cpu.time_model_metrics:
            lines.append("\n  Time Model Breakdown:")
            lines.append(f"    {'Stat Name':<40} {'Time (s)':>12} {'% of DB Time':>15}")
            lines.append("    " + "-" * 70)
            for tm in cpu.time_model_metrics[:15]:
                pct_str = f"{tm.pct_of_db_time:.2f}%" if tm.pct_of_db_time is not None else "N/A"
                lines.append(f"    {tm.stat_name:<40} {tm.time_seconds:>12.4f} {pct_str:>15}")
    else:
        lines.append("\n[2] CPU USAGE STATISTICS: Not requested or unavailable")

    # 3. I/O Statistics
    if report.io_stats is not None:
        io = report.io_stats
        lines.append(f"\n[3] I/O STATISTICS (Source: {io.source_view})")
        lines.append("-" * 80)
        if io.tablespace_summaries:
            lines.append("  Tablespace I/O Aggregates:")
            lines.append(f"    {'Tablespace':<20} {'Reads':>10} {'Writes':>10} {'Read ms':>12} {'Write ms':>12} {'Avg R Lat ms':>14} {'Avg W Lat ms':>14}")
            lines.append("    " + "-" * 96)
            for ts in io.tablespace_summaries:
                lines.append(f"    {ts.tablespace_name:<20} {ts.physical_reads:>10,d} {ts.physical_writes:>10,d} {ts.read_time_ms:>12.2f} {ts.write_time_ms:>12.2f} {ts.avg_read_latency_ms:>14.2f} {ts.avg_write_latency_ms:>14.2f}")

        if io.file_stats:
            lines.append("\n  Data & Temp File Performance:")
            lines.append(f"    {'File ID':<8} {'Type':<6} {'Reads':>10} {'Writes':>10} {'Avg R ms':>10} {'Avg W ms':>10} {'File Name'}")
            lines.append("    " + "-" * 90)
            for f in io.file_stats:
                fid_str = str(f.file_id) if f.file_id is not None else "N/A"
                lines.append(f"    {fid_str:<8} {f.file_type:<6} {f.physical_reads:>10,d} {f.physical_writes:>10,d} {f.avg_read_latency_ms:>10.2f} {f.avg_write_latency_ms:>10.2f} {f.file_name}")

        if io.iostat_functions:
            lines.append("\n  I/O by Database Function:")
            lines.append(f"    {'Function':<20} {'Reads':>10} {'Writes':>10} {'Read Time ms':>14} {'Write Time ms':>14}")
            lines.append("    " + "-" * 72)
            for fn in io.iostat_functions:
                lines.append(f"    {fn.function_name:<20} {fn.physical_reads:>10,d} {fn.physical_writes:>10,d} {fn.read_time_ms:>14.2f} {fn.write_time_ms:>14.2f}")
    else:
        lines.append("\n[3] I/O STATISTICS: Not requested or unavailable")

    # 4. Latch Statistics
    if report.latch_stats is not None:
        lat = report.latch_stats
        lines.append("\n[4] LATCH CONTENTION & MISS STATISTICS")
        lines.append("-" * 80)
        if lat.latches:
            lines.append(f"  {'Latch Name':<32} {'Gets':>10} {'Misses':>10} {'Sleeps':>8} {'Wait ms':>10} {'Hit Ratio':>10} {'Sleep Rate':>11}")
            lines.append("  " + "-" * 96)
            for l_item in lat.latches:
                lines.append(f"  {l_item.name:<32} {l_item.gets:>10,d} {l_item.misses:>10,d} {l_item.sleeps:>8,d} {l_item.wait_time_ms:>10.2f} {l_item.hit_ratio_pct:>9.2f}% {l_item.sleep_rate_pct:>10.2f}%")
        else:
            lines.append("  No latch contention detected.")

        if lat.latch_misses:
            lines.append("\n  Top Latch Miss Locations:")
            lines.append(f"    {'Parent Latch':<28} {'NW Failures':>12} {'Sleeps':>10} {'Where in Code'}")
            lines.append("    " + "-" * 78)
            for miss in lat.latch_misses[:10]:
                lines.append(f"    {miss.parent_name:<28} {miss.nwfail_count:>12,d} {miss.sleep_count:>10,d} {miss.where_in_code}")
    else:
        lines.append("\n[4] LATCH STATISTICS: Not requested or unavailable")

    # 5. High Parse SQL & Offending SQL
    if report.high_parse_sql is not None:
        hps = report.high_parse_sql
        lines.append("\n[5] HIGH SQL PARSE RATES & OFFENDING SQL DIAGNOSIS")
        lines.append("-" * 80)
        if hps.system_parse_metrics:
            spm = hps.system_parse_metrics
            lines.append(f"Total Parses: {spm.parse_count_total:,} | Hard Parses: {spm.parse_count_hard:,} ({spm.hard_parse_pct:.2f}%) | Failed Parses: {spm.parse_count_failures:,}")
            lines.append(f"Parse CPU Time: {spm.parse_time_cpu_seconds:.2f}s | Session Cursor Cache Hits: {spm.session_cursor_cache_hits:,} ({spm.cursor_cache_hit_pct:.2f}%)")

        if hps.overall_recommendations:
            lines.append("\n  Overall Parse Recommendations:")
            for rec in hps.overall_recommendations:
                lines.append(f"  * {rec}")

        if hps.offending_sql:
            lines.append("\n  Offending SQL Statements:")
            for idx, sql_item in enumerate(hps.offending_sql, 1):
                lines.append(f"\n  ({idx}) SQL_ID: {sql_item.sql_id} [Module: {sql_item.module or 'N/A'}]")
                lines.append(f"      Parses: {sql_item.parse_calls:,} | Executions: {sql_item.executions:,} | Parse/Exec Ratio: {sql_item.parse_per_exec_ratio:.2f} | Versions: {sql_item.version_count} | Invalidations: {sql_item.invalidations}")
                lines.append(f"      CPU Time: {sql_item.cpu_time_ms:.2f}ms | Elapsed Time: {sql_item.elapsed_time_ms:.2f}ms")
                lines.append(f"      SQL: {sql_item.sql_text}")
                lines.append("      Diagnosis & Recommendations:")
                for diag in sql_item.diagnoses:
                    lines.append(f"        -> {diag}")
        else:
            lines.append("  No statements exceeded the parse threshold.")
    else:
        lines.append("\n[5] HIGH SQL PARSE RATES: Not requested or unavailable")

    lines.append("\n" + "=" * 80)
    lines.append("END OF SYSTEM METRICS DIAGNOSTICS REPORT")
    lines.append("=" * 80)

    return "\n".join(lines)


class TyperApp(typer.Typer):
    """Typer application with parse_args support for programmatic parsing."""

    def parse_args(self, args: Sequence[str] | None = None) -> SimpleNamespace:
        """Parse arguments into a namespace for programmatic use.

        Args:
            args (Sequence[str] | None): Arguments to parse.

        Returns:
            SimpleNamespace: Namespace of parsed arguments.
        """
        cmd = typer.main.get_command(self)
        ctx = cmd.make_context("oracle_system_metrics_diagnostics", list(args) if args is not None else sys.argv[1:])
        ns = SimpleNamespace(**ctx.params)
        if hasattr(ns, "output") and not hasattr(ns, "output_file"):
            ns.output_file = ns.output
        elif hasattr(ns, "output_file") and not hasattr(ns, "output"):
            ns.output = ns.output_file
        return ns


app = TyperApp(add_completion=False, help="Oracle database system metrics and SQL parse diagnostics analyzer.")


@app.command()
def run(
    user: str | None = typer.Option(
        None,
        "-u",
        "--user",
        envvar="ORACLE_USER",
        help="Database username (default: ORACLE_USER)",
    ),
    password: str | None = typer.Option(
        None,
        "-p",
        "--password",
        envvar="ORACLE_PASSWORD",
        help="Database password (default: ORACLE_PASSWORD)",
    ),
    host: str = typer.Option(
        "localhost",
        "--host",
        envvar="ORACLE_HOST",
        help="Oracle database host (default: ORACLE_HOST or localhost)",
    ),
    port: int = typer.Option(
        1521,
        "--port",
        envvar="ORACLE_PORT",
        help="Oracle database port (default: ORACLE_PORT or 1521)",
    ),
    service_name: str | None = typer.Option(
        None,
        "--service-name",
        envvar="ORACLE_SERVICE_NAME",
        help="Oracle service name (default: ORACLE_SERVICE_NAME)",
    ),
    sid: str | None = typer.Option(
        None,
        "--sid",
        envvar="ORACLE_SID",
        help="Oracle SID (default: ORACLE_SID)",
    ),
    sysdba: bool = typer.Option(
        False,
        "--sysdba",
        help="Connect with SYSDBA privilege",
    ),
    analyzer: str = typer.Option(
        "all",
        "--analyzer",
        help="Select analyzer module to run (default: all)",
    ),
    top: int = typer.Option(
        20,
        "--top",
        help="Top N rows to return for ranked metrics (default: 20)",
    ),
    min_parses: int = typer.Option(
        100,
        "--min-parses",
        help="Minimum parse count threshold for offending SQL queries (default: 100)",
    ),
    format: str = typer.Option(
        "text",
        "--format",
        help="Output report format (default: text)",
    ),
    output_file: str | None = typer.Option(
        None,
        "-o",
        "--output",
        "--output-file",
        help="File path to save the output report",
    ),
) -> int:
    """Execute system metrics analysis and output the report.

    Args:
        user (str | None): Database username.
        password (str | None): Database password.
        host (str): Database hostname.
        port (int): Database port.
        service_name (str | None): Oracle service name.
        sid (str | None): Oracle SID.
        sysdba (bool): Whether to connect with SYSDBA privilege.
        analyzer (str): Analyzer module to run.
        top (int): Top N rows to return for ranked metrics.
        min_parses (int): Minimum parse count threshold.
        format (str): Output report format (text or json).
        output_file (str | None): File path to save output report.

    Returns:
        int: Exit status code.
    """
    if not user:
        logger.error("Database username must be specified via -u/--user or ORACLE_USER")
        return 1
    if not password:
        logger.error("Database password must be specified via -p/--password or ORACLE_PASSWORD")
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
        )
    except ValidationError as exc:
        logger.error("Configuration validation failed: {}", exc)
        return 1

    driver = OracleDriver(config)
    metrics_analyzer = OracleSystemMetricsAnalyzer(
        driver=driver,
        top_n=top,
        min_parses=min_parses,
    )

    try:
        if analyzer == "all":
            report = metrics_analyzer.run_all()
        else:
            report = SystemMetricsDiagnosticsReport()
            if analyzer == "buffer_pool":
                report.buffer_pool = metrics_analyzer.analyze_buffer_pool()
            elif analyzer == "cpu_usage":
                report.cpu_usage = metrics_analyzer.analyze_cpu_usage()
            elif analyzer == "io_stats":
                report.io_stats = metrics_analyzer.analyze_io_stats()
            elif analyzer == "latch_stats":
                report.latch_stats = metrics_analyzer.analyze_latch_stats()
            elif analyzer == "high_parse_sql":
                report.high_parse_sql = metrics_analyzer.analyze_high_parse_sql()
    except oracledb.DatabaseError as exc:
        logger.error("Database error during system metrics collection: {}", exc)
        return 1

    if format == "json":
        output_text = report.model_dump_json(indent=2)
    else:
        output_text = format_system_metrics_report_text(report)

    if output_file:
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(output_text)
            logger.info("Diagnostics report saved to {}", output_file)
        except OSError as exc:
            logger.error("Failed to write report to {}: {}", output_file, exc)
            return 1
    else:
        sys.stdout.write(output_text + "\n")

    return 0


def build_parser() -> TyperApp:
    """Construct CLI argument parser for system metrics diagnostics analyzer.

    Returns:
        TyperApp: Configured Typer application.
    """
    return app


def main(argv: Sequence[str] | None = None) -> int:
    """CLI execution entrypoint.

    Args:
        argv (Sequence[str] | None): Command-line argument list, or None for sys.argv[1:].

    Returns:
        int: Exit status code.
    """
    try:
        if argv is not None:
            args = list(argv[1:]) if len(argv) > 0 and argv[0].endswith(".py") else list(argv)
        else:
            args = None
        ret = app(args=args, standalone_mode=False)
        return 0 if ret is None else int(ret)
    except typer.Exit as exc:
        return exc.exit_code
    except (typer.BadParameter, typer.exceptions.TyperException) as exc:
        sys.exit(getattr(exc, "exit_code", 2))
    except Exception as exc:
        logger.error("{}", exc)
        return 1


if __name__ == "__main__":
    app()
