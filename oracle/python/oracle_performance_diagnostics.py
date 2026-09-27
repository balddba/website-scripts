#!/usr/bin/env python3
#===============================================================================
#
# Script Name: oracle_performance_diagnostics.py
# Title: Oracle performance diagnostics
# Tags: Python, Diagnostics, Performance
# Purpose: Diagnose Oracle latch, buffer, wait, and blocking-lock behavior.
#
# Description:
#   Collects performance metrics and blocking-lock details and provides
#   root-cause-oriented tuning recommendations.
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
#   python oracle_performance_diagnostics.py --help
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
"""Oracle database performance diagnostics analyzer.

Provides diagnostics for latch waits, buffer pool statistics, buffer busy waits
with root-cause tuning recommendations, and locked objects with blocking lock hierarchies.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import oracledb
from loguru import logger
from pydantic import BaseModel, Field, SecretStr, ValidationError

LOCK_MODE_NAMES: dict[int, str] = {
    0: "None (0)",
    1: "Null (1)",
    2: "Row-S / SS (2)",
    3: "Row-X / SX (3)",
    4: "Share / S (4)",
    5: "S/Row-X / SSX (5)",
    6: "Exclusive / X (6)",
}


def get_lock_mode_name(mode_code: int | None) -> str:
    """Convert an Oracle lock mode code into a readable name.

    Args:
        mode_code (int | None): Oracle numeric lock mode (0-6).

    Returns:
        str: Human-readable lock mode description.
    """
    if mode_code is None:
        return "None (0)"
    return LOCK_MODE_NAMES.get(mode_code, f"Unknown ({mode_code})")


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


class LatchWaitMetric(BaseModel):
    """Latch acquisition and wait statistics from V$LATCH.

    Attributes:
        name: Name of the latch.
        gets: Number of willing-to-wait get requests.
        misses: Number of times willing-to-wait get failed on first attempt.
        sleeps: Number of times willing-to-wait sleep occurred.
        immediate_gets: Number of immediate get requests.
        immediate_misses: Number of failed immediate get requests.
        wait_time_ms: Total time waited for latch in milliseconds.
        hit_ratio_pct: Latch hit ratio percentage ((gets - misses) / gets * 100).
    """

    model_config = {"extra": "forbid"}

    name: str
    gets: int
    misses: int
    sleeps: int
    immediate_gets: int
    immediate_misses: int
    wait_time_ms: float
    hit_ratio_pct: float


class BufferPoolSummary(BaseModel):
    """Buffer pool operational and sizing metrics from V$BUFFER_POOL_STATISTICS.

    Attributes:
        pool_name: Buffer pool identifier (e.g. DEFAULT, KEEP, RECYCLE).
        block_size_bytes: Block size in bytes for the pool.
        size_mb: Total buffer pool size in megabytes.
        physical_reads: Number of physical data block reads.
        db_block_gets: Number of current block gets.
        consistent_gets: Number of consistent read gets.
        physical_writes: Number of physical data block writes.
        free_buffer_waits: Count of free buffer wait occurrences.
        write_complete_waits: Count of write complete wait occurrences.
        hit_ratio_pct: Buffer cache hit ratio percentage.
    """

    model_config = {"extra": "forbid"}

    pool_name: str
    block_size_bytes: int
    size_mb: float
    physical_reads: int
    db_block_gets: int
    consistent_gets: int
    physical_writes: int
    free_buffer_waits: int
    write_complete_waits: int
    hit_ratio_pct: float


class WaitStatMetric(BaseModel):
    """Buffer wait statistics breakdown by block class from V$WAITSTAT.

    Attributes:
        class_name: Block class name (e.g. data block, segment header).
        count: Total number of waits for this class.
        time_waited_ms: Total time waited in milliseconds.
    """

    model_config = {"extra": "forbid"}

    class_name: str
    count: int
    time_waited_ms: float


class WaitEventStat(BaseModel):
    """System wait event metrics from V$SYSTEM_EVENT.

    Attributes:
        event_name: Wait event name.
        total_waits: Total number of waits for the event.
        time_waited_ms: Total time waited in milliseconds.
        avg_wait_ms: Average wait duration in milliseconds.
    """

    model_config = {"extra": "forbid"}

    event_name: str
    total_waits: int
    time_waited_ms: float
    avg_wait_ms: float


class BufferBusyWaitAnalysis(BaseModel):
    """Buffer busy wait analysis and tuning recommendations.

    Attributes:
        wait_stats: Block class wait statistics.
        system_events: Related system wait events.
        tuning_recommendations: Root-cause diagnostic recommendations.
    """

    model_config = {"extra": "forbid"}

    wait_stats: list[WaitStatMetric] = Field(default_factory=list)
    system_events: list[WaitEventStat] = Field(default_factory=list)
    tuning_recommendations: list[str] = Field(default_factory=list)


class LockedObjectDetail(BaseModel):
    """Details of an object currently locked in the database.

    Attributes:
        sid: Oracle session identifier holding or requesting the lock.
        serial_number: Session serial number.
        username: Database username of session.
        osuser: Operating system user.
        machine: Client machine identifier.
        program: Client application or process name.
        object_owner: Schema owner of locked object.
        object_name: Name of locked object.
        object_type: Type of locked object (e.g. TABLE, INDEX).
        lock_mode_held_code: Numeric code of lock mode held.
        lock_mode_held: Readable name of lock mode held.
        lock_mode_requested_code: Numeric code of lock mode requested.
        lock_mode_requested: Readable name of lock mode requested.
        blocking_sid: Session ID blocking this session, if any.
        wait_seconds: Duration waited in seconds.
        current_sql_id: SQL ID currently or previously executed.
    """

    model_config = {"extra": "forbid"}

    sid: int
    serial_number: int
    username: str | None = None
    osuser: str | None = None
    machine: str | None = None
    program: str | None = None
    object_owner: str
    object_name: str
    object_type: str
    lock_mode_held_code: int
    lock_mode_held: str
    lock_mode_requested_code: int
    lock_mode_requested: str
    blocking_sid: int | None = None
    wait_seconds: int | None = None
    current_sql_id: str | None = None


class BlockingHierarchyNode(BaseModel):
    """Hierarchical node representing a blocking session and its direct dependents.

    Attributes:
        sid: Session ID.
        serial_number: Session serial number.
        username: Database username.
        program: Program name.
        sql_id: Current or previous SQL ID.
        wait_seconds: Duration waited in seconds.
        blocked_sids: List of session IDs directly blocked by this session.
    """

    model_config = {"extra": "forbid"}

    sid: int
    serial_number: int
    username: str | None = None
    program: str | None = None
    sql_id: str | None = None
    wait_seconds: int | None = None
    blocked_sids: list[int] = Field(default_factory=list)


class LockedObjectsReport(BaseModel):
    """Consolidated report for locked objects and blocking locks.

    Attributes:
        locked_objects: List of locked object details.
        blocking_chains: Blocking hierarchy nodes.
        root_blockers: Session IDs identified as root blockers.
    """

    model_config = {"extra": "forbid"}

    locked_objects: list[LockedObjectDetail] = Field(default_factory=list)
    blocking_chains: list[BlockingHierarchyNode] = Field(default_factory=list)
    root_blockers: list[int] = Field(default_factory=list)


class PerformanceDiagnosticsReport(BaseModel):
    """Consolidated performance diagnostics report across all analyzers.

    Attributes:
        timestamp: Analysis execution timestamp.
        latch_summary: Latch wait and contention summary.
        buffer_pool_summary: Buffer pool sizing and cache efficiency metrics.
        buffer_busy_waits: Buffer busy wait statistics and recommendations.
        locked_objects_report: Locked objects and blocking lock hierarchy.
    """

    model_config = {"extra": "forbid"}

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    latch_summary: list[LatchWaitMetric] = Field(default_factory=list)
    buffer_pool_summary: list[BufferPoolSummary] = Field(default_factory=list)
    buffer_busy_waits: BufferBusyWaitAnalysis | None = None
    locked_objects_report: LockedObjectsReport | None = None


class OracleDriver:
    """Manages connections and session lifecycle for Oracle database."""

    def __init__(self, config: OracleConnectionConfig) -> None:
        """Initialize driver with connection settings.

        Args:
            config: Oracle connection settings and credentials.
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


class OraclePerformanceAnalyzer:
    """Performs database performance diagnostics and analyzes wait events."""

    def __init__(self, driver: OracleDriver, top_n: int = 20) -> None:
        """Initialize analyzer with driver and analysis parameters.

        Args:
            driver: Database driver providing session management.
            top_n: Maximum number of rows to return for ranked metrics.
        """
        self._driver = driver
        self._top_n = top_n

    def analyze_latch_summary(self) -> list[LatchWaitMetric]:
        """Query V$LATCH for latch contention and wait statistics.

        Returns:
            list[LatchWaitMetric]: Top latches ranked by sleeps and wait time.
        """
        sql = """
            SELECT * FROM (
                SELECT
                    name,
                    gets,
                    misses,
                    sleeps,
                    immediate_gets,
                    immediate_misses,
                    ROUND(wait_time / 1000, 2) AS wait_time_ms,
                    CASE
                        WHEN gets > 0 THEN ROUND(((gets - misses) / gets) * 100, 2)
                        ELSE 100.0
                    END AS hit_ratio_pct
                FROM v$latch
                WHERE gets > 0 OR misses > 0 OR sleeps > 0 OR immediate_gets > 0
                ORDER BY sleeps DESC, wait_time DESC
            )
            WHERE ROWNUM <= :top_n
        """
        results: list[LatchWaitMetric] = []
        try:
            with self._driver.session() as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(sql, {"top_n": self._top_n})
                    rows = cursor.fetchall()
                except oracledb.DatabaseError as exc:
                    logger.error("Failed to query V$LATCH: {}", exc)
                    raise

                for row in rows:
                    results.append(
                        LatchWaitMetric(
                            name=str(row[0]),
                            gets=int(row[1] or 0),
                            misses=int(row[2] or 0),
                            sleeps=int(row[3] or 0),
                            immediate_gets=int(row[4] or 0),
                            immediate_misses=int(row[5] or 0),
                            wait_time_ms=float(row[6] or 0.0),
                            hit_ratio_pct=float(row[7] or 100.0),
                        )
                    )
        except oracledb.DatabaseError as exc:
            if "ORA-00942" in str(exc):
                logger.warning("V$LATCH view not accessible: {}", exc)
                return []
            raise

        return results

    def analyze_buffer_pool(self) -> list[BufferPoolSummary]:
        """Query buffer pool statistics and hit ratios.

        Returns:
            list[BufferPoolSummary]: Sizing and performance metrics per buffer pool.
        """
        sql = """
            SELECT
                COALESCE(s.name, b.name, 'DEFAULT') AS pool_name,
                COALESCE(s.block_size, b.block_size, 8192) AS block_size,
                ROUND(COALESCE(s.buffers, b.buffers, 0) * COALESCE(s.block_size, b.block_size, 8192) / (1024 * 1024), 2) AS size_mb,
                COALESCE(s.physical_reads, 0) AS physical_reads,
                COALESCE(s.db_block_gets, 0) AS db_block_gets,
                COALESCE(s.consistent_gets, 0) AS consistent_gets,
                COALESCE(s.physical_writes, 0) AS physical_writes,
                COALESCE(s.free_buffer_wait, 0) AS free_buffer_wait,
                COALESCE(s.write_complete_wait, 0) AS write_complete_wait,
                CASE
                    WHEN (COALESCE(s.db_block_gets, 0) + COALESCE(s.consistent_gets, 0)) > 0
                    THEN ROUND((1 - (COALESCE(s.physical_reads, 0) / (COALESCE(s.db_block_gets, 0) + COALESCE(s.consistent_gets, 0)))) * 100, 2)
                    ELSE 100.0
                END AS hit_ratio_pct
            FROM v$buffer_pool_statistics s
            FULL OUTER JOIN v$buffer_pool b ON s.name = b.name AND s.block_size = b.block_size
            ORDER BY pool_name
        """
        results: list[BufferPoolSummary] = []
        try:
            with self._driver.session() as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(sql)
                    rows = cursor.fetchall()
                except oracledb.DatabaseError as exc:
                    logger.error("Failed to query V$BUFFER_POOL_STATISTICS: {}", exc)
                    raise

                for row in rows:
                    results.append(
                        BufferPoolSummary(
                            pool_name=str(row[0]),
                            block_size_bytes=int(row[1] or 8192),
                            size_mb=float(row[2] or 0.0),
                            physical_reads=int(row[3] or 0),
                            db_block_gets=int(row[4] or 0),
                            consistent_gets=int(row[5] or 0),
                            physical_writes=int(row[6] or 0),
                            free_buffer_waits=int(row[7] or 0),
                            write_complete_waits=int(row[8] or 0),
                            hit_ratio_pct=float(row[9] or 100.0),
                        )
                    )
        except oracledb.DatabaseError as exc:
            if "ORA-00942" in str(exc):
                logger.warning("V$BUFFER_POOL_STATISTICS view not accessible: {}", exc)
                return []
            raise

        return results

    def analyze_buffer_busy_waits(self) -> BufferBusyWaitAnalysis:
        """Query V$WAITSTAT and V$SYSTEM_EVENT to diagnose buffer busy waits.

        Returns:
            BufferBusyWaitAnalysis: Wait statistics and root-cause tuning suggestions.
        """
        waitstat_sql = """
            SELECT
                class AS class_name,
                count,
                ROUND(time * 10, 2) AS time_waited_ms
            FROM v$waitstat
            WHERE count > 0
            ORDER BY time DESC, count DESC
        """
        events_sql = """
            SELECT
                event AS event_name,
                total_waits,
                ROUND(time_waited_micro / 1000, 2) AS time_waited_ms,
                CASE
                    WHEN total_waits > 0 THEN ROUND((time_waited_micro / 1000) / total_waits, 2)
                    ELSE 0.0
                END AS avg_wait_ms
            FROM v$system_event
            WHERE event IN (
                'buffer busy waits',
                'read by other session',
                'write complete waits',
                'free buffer waits'
            )
            ORDER BY time_waited_micro DESC
        """
        wait_stats: list[WaitStatMetric] = []
        system_events: list[WaitEventStat] = []

        try:
            with self._driver.session() as conn, conn.cursor() as cursor:
                try:
                    cursor.execute(waitstat_sql)
                    for row in cursor.fetchall():
                        wait_stats.append(
                            WaitStatMetric(
                                class_name=str(row[0]),
                                count=int(row[1] or 0),
                                time_waited_ms=float(row[2] or 0.0),
                            )
                        )
                except oracledb.DatabaseError as exc:
                    if "ORA-00942" in str(exc):
                        logger.warning("V$WAITSTAT view not accessible: {}", exc)
                    else:
                        logger.error("Failed to query V$WAITSTAT: {}", exc)
                        raise

                try:
                    cursor.execute(events_sql)
                    for row in cursor.fetchall():
                        system_events.append(
                            WaitEventStat(
                                event_name=str(row[0]),
                                total_waits=int(row[1] or 0),
                                time_waited_ms=float(row[2] or 0.0),
                                avg_wait_ms=float(row[3] or 0.0),
                            )
                        )
                except oracledb.DatabaseError as exc:
                    if "ORA-00942" in str(exc):
                        logger.warning("V$SYSTEM_EVENT view not accessible: {}", exc)
                    else:
                        logger.error("Failed to query V$SYSTEM_EVENT: {}", exc)
                        raise
        except oracledb.DatabaseError as exc:
            if "ORA-00942" in str(exc):
                logger.warning("Wait views not accessible: {}", exc)
            else:
                raise

        recommendations = self._generate_buffer_tuning_suggestions(wait_stats, system_events)
        return BufferBusyWaitAnalysis(
            wait_stats=wait_stats,
            system_events=system_events,
            tuning_recommendations=recommendations,
        )

    def _generate_buffer_tuning_suggestions(
        self,
        wait_stats: list[WaitStatMetric],
        system_events: list[WaitEventStat],
    ) -> list[str]:
        """Generate tuning recommendations based on wait statistics.

        Args:
            wait_stats: Block class wait statistics.
            system_events: System wait events.

        Returns:
            list[str]: Root-cause recommendations.
        """
        suggestions: list[str] = []
        classes_with_waits = {ws.class_name.lower(): ws for ws in wait_stats if ws.count > 0}
        event_dict = {se.event_name.lower(): se for se in system_events if se.total_waits > 0}

        if "data block" in classes_with_waits:
            suggestions.append("Data Block Contention: High concurrency on identical table or index data blocks. Consider using Automatic Segment Space Management (ASSM), partitioning hot tables/indexes, increasing PCTFREE to reduce rows per block, or tuning high-concurrency SQL queries.")

        if "segment header" in classes_with_waits:
            suggestions.append("Segment Header Contention: Bottleneck on segment header blocks during concurrent inserts. For manual space management tablespaces, increase FREELISTS and FREELIST GROUPS on hot tables/indexes, or migrate the tablespace to ASSM (Automatic Segment Space Management).")

        if "undo header" in classes_with_waits:
            suggestions.append("Undo Header Contention: Contention allocating transaction table slots in undo segment headers. Ensure Automatic Undo Management is enabled (UNDO_MANAGEMENT=AUTO) and size the UNDO tablespace adequately.")

        if "undo block" in classes_with_waits:
            suggestions.append("Undo Block Contention: Multiple sessions accessing or generating undo blocks simultaneously. Increase UNDO_RETENTION, resize UNDO tablespace, and optimize long-running transactions.")

        if "free list" in classes_with_waits:
            suggestions.append("Free List Contention: Process contention allocating blocks from freelists. Increase FREELISTS / FREELIST GROUPS on affected objects or convert tablespace to ASSM.")

        if "read by other session" in event_dict:
            suggestions.append("Read By Other Session Contention: Multiple sessions waiting for the same block being read from disk. Tune queries performing full table or large index scans, and consider indexing to avoid repetitive scans.")

        if "free buffer waits" in event_dict or "write complete waits" in event_dict:
            suggestions.append("DBWR / Checkpoint Latency: Sessions stalling waiting for clean buffers. Consider increasing DB_WRITER_PROCESSES, reviewing I/O throughput, or tuning checkpoint frequencies.")

        if not suggestions:
            suggestions.append("No significant buffer busy wait bottlenecks detected. Ensure sequence caching is optimized (e.g. CACHE >= 1000) for high-rate insert workloads.")
        else:
            suggestions.append("Sequence Caching: Verify sequences used in hot insert tables are cached (CACHE >= 1000, NOORDER) to minimize dictionary row cache and block contention.")

        return suggestions

    def analyze_locked_objects(self) -> LockedObjectsReport:
        """Query locked objects, lock modes, and construct blocking lock hierarchy.

        Returns:
            LockedObjectsReport: Locked objects and hierarchical blocking relationships.
        """
        # Attempt query using DBA_OBJECTS first, fallback to ALL_OBJECTS on ORA-00942
        objects_views = ["dba_objects", "all_objects"]
        rows: list[tuple[Any, ...]] = []
        session_rows: list[tuple[Any, ...]] = []

        with self._driver.session() as conn, conn.cursor() as cursor:
            for view_name in objects_views:
                locked_sql = f"""
                    SELECT
                        lo.session_id AS sid,
                        COALESCE(s.serial#, 0) AS serial_number,
                        s.username,
                        s.osuser,
                        s.machine,
                        s.program,
                        do.owner AS object_owner,
                        do.object_name,
                        do.object_type,
                        lo.locked_mode AS lock_mode_held_code,
                        COALESCE(l.request, 0) AS lock_mode_requested_code,
                        s.blocking_session AS blocking_sid,
                        s.seconds_in_wait AS wait_seconds,
                        COALESCE(s.sql_id, s.prev_sql_id) AS current_sql_id
                    FROM v$locked_object lo
                    JOIN {view_name} do ON lo.object_id = do.object_id
                    LEFT JOIN v$session s ON lo.session_id = s.sid
                    LEFT JOIN v$lock l ON lo.session_id = l.sid AND lo.object_id = l.id1
                    ORDER BY lo.session_id, do.owner, do.object_name
                """
                try:
                    cursor.execute(locked_sql)
                    rows = cursor.fetchall()
                    break
                except oracledb.DatabaseError as exc:
                    if "ORA-00942" in str(exc) and view_name == "dba_objects":
                        logger.warning("DBA_OBJECTS not accessible, falling back to ALL_OBJECTS")
                        continue
                    if "ORA-00942" in str(exc):
                        logger.warning("Locked object views not accessible: {}", exc)
                        return LockedObjectsReport()
                    logger.error("Failed to query locked objects: {}", exc)
                    raise

            # Query blocking session hierarchy from V$SESSION
            session_sql = """
                SELECT
                    s.sid,
                    s.serial# AS serial_number,
                    s.username,
                    s.program,
                    COALESCE(s.sql_id, s.prev_sql_id) AS sql_id,
                    s.seconds_in_wait AS wait_seconds,
                    s.blocking_session AS blocking_sid
                FROM v$session s
                WHERE s.blocking_session IS NOT NULL OR s.sid IN (
                    SELECT DISTINCT blocking_session
                    FROM v$session
                    WHERE blocking_session IS NOT NULL
                )
                ORDER BY s.sid
            """
            try:
                cursor.execute(session_sql)
                session_rows = cursor.fetchall()
            except oracledb.DatabaseError as exc:
                if "ORA-00942" in str(exc):
                    logger.warning("V$SESSION view not accessible for hierarchy: {}", exc)
                else:
                    logger.error("Failed to query V$SESSION for blocking locks: {}", exc)
                    raise

        locked_objects: list[LockedObjectDetail] = []
        for r in rows:
            held_code = int(r[9] or 0)
            req_code = int(r[10] or 0)
            locked_objects.append(
                LockedObjectDetail(
                    sid=int(r[0]),
                    serial_number=int(r[1] or 0),
                    username=str(r[2]) if r[2] is not None else None,
                    osuser=str(r[3]) if r[3] is not None else None,
                    machine=str(r[4]) if r[4] is not None else None,
                    program=str(r[5]) if r[5] is not None else None,
                    object_owner=str(r[6] or ""),
                    object_name=str(r[7] or ""),
                    object_type=str(r[8] or ""),
                    lock_mode_held_code=held_code,
                    lock_mode_held=get_lock_mode_name(held_code),
                    lock_mode_requested_code=req_code,
                    lock_mode_requested=get_lock_mode_name(req_code),
                    blocking_sid=int(r[11]) if r[11] is not None else None,
                    wait_seconds=int(r[12]) if r[12] is not None else None,
                    current_sql_id=str(r[13]) if r[13] is not None else None,
                )
            )

        blocking_chains, root_blockers = self._build_blocking_hierarchy(session_rows, locked_objects)

        return LockedObjectsReport(
            locked_objects=locked_objects,
            blocking_chains=blocking_chains,
            root_blockers=root_blockers,
        )

    def _build_blocking_hierarchy(
        self,
        session_rows: list[tuple[Any, ...]],
        locked_objects: list[LockedObjectDetail],
    ) -> tuple[list[BlockingHierarchyNode], list[int]]:
        """Construct blocking chains and determine root blockers.

        Args:
            session_rows: Raw rows from V$SESSION containing blocker and waiter information.
            locked_objects: List of parsed locked object details.

        Returns:
            tuple[list[BlockingHierarchyNode], list[int]]: Blocking nodes and root blocker SIDs.
        """
        sessions_by_sid: dict[int, dict[str, Any]] = {}
        blocked_by: dict[int, list[int]] = {}

        for row in session_rows:
            sid = int(row[0])
            serial = int(row[1] or 0)
            username = str(row[2]) if row[2] is not None else None
            program = str(row[3]) if row[3] is not None else None
            sql_id = str(row[4]) if row[4] is not None else None
            wait_seconds = int(row[5]) if row[5] is not None else None
            blocking_sid = int(row[6]) if row[6] is not None else None

            sessions_by_sid[sid] = {
                "sid": sid,
                "serial_number": serial,
                "username": username,
                "program": program,
                "sql_id": sql_id,
                "wait_seconds": wait_seconds,
                "blocking_sid": blocking_sid,
            }
            if blocking_sid is not None:
                blocked_by.setdefault(blocking_sid, []).append(sid)

        # Incorporate information from locked objects if session view did not return them
        for lo in locked_objects:
            if lo.sid not in sessions_by_sid:
                sessions_by_sid[lo.sid] = {
                    "sid": lo.sid,
                    "serial_number": lo.serial_number,
                    "username": lo.username,
                    "program": lo.program,
                    "sql_id": lo.current_sql_id,
                    "wait_seconds": lo.wait_seconds,
                    "blocking_sid": lo.blocking_sid,
                }
            if lo.blocking_sid is not None and lo.sid not in blocked_by.get(lo.blocking_sid, []):
                blocked_by.setdefault(lo.blocking_sid, []).append(lo.sid)

        nodes: list[BlockingHierarchyNode] = []
        for sid, data in sessions_by_sid.items():
            nodes.append(
                BlockingHierarchyNode(
                    sid=sid,
                    serial_number=data["serial_number"],
                    username=data["username"],
                    program=data["program"],
                    sql_id=data["sql_id"],
                    wait_seconds=data["wait_seconds"],
                    blocked_sids=blocked_by.get(sid, []),
                )
            )

        # Identify root blockers (sessions that block others but are not blocked themselves)
        all_blockers = set(blocked_by.keys())
        all_blocked = {s["sid"] for s in sessions_by_sid.values() if s["blocking_sid"] is not None}
        root_blockers = sorted(all_blockers - all_blocked)

        return sorted(nodes, key=lambda n: n.sid), root_blockers

    def run_all(self) -> PerformanceDiagnosticsReport:
        """Run all performance diagnostic analyzers and assemble report.

        Returns:
            PerformanceDiagnosticsReport: Complete diagnostic metrics.
        """
        logger.info("Executing Oracle performance diagnostic analyzers")
        latch_summary = self.analyze_latch_summary()
        buffer_pool_summary = self.analyze_buffer_pool()
        buffer_busy_waits = self.analyze_buffer_busy_waits()
        locked_objects_report = self.analyze_locked_objects()

        return PerformanceDiagnosticsReport(
            latch_summary=latch_summary,
            buffer_pool_summary=buffer_pool_summary,
            buffer_busy_waits=buffer_busy_waits,
            locked_objects_report=locked_objects_report,
        )


def format_performance_report_text(report: PerformanceDiagnosticsReport) -> str:
    """Render performance diagnostics report in formatted text.

    Args:
        report (PerformanceDiagnosticsReport): Report containing diagnostic metrics.

    Returns:
        str: Formatted human-readable report.
    """
    lines: list[str] = [
        "=" * 80,
        "ORACLE PERFORMANCE DIAGNOSTICS REPORT",
        f"Generated At (UTC): {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 80,
    ]

    # 1. Latch Wait Summary
    lines.append("\n" + "-" * 80)
    lines.append("1. LATCH WAIT AND CONTENTION SUMMARY")
    lines.append("-" * 80)
    if report.latch_summary:
        lines.append(f"{'Latch Name':<32} {'Gets':>10} {'Misses':>10} {'Sleeps':>8} {'Wait (ms)':>10} {'Hit Ratio %':>12}")
        lines.append("-" * 86)
        for latch in report.latch_summary:
            lines.append(f"{latch.name[:32]:<32} {latch.gets:>10d} {latch.misses:>10d} {latch.sleeps:>8d} {latch.wait_time_ms:>10.2f} {latch.hit_ratio_pct:>11.2f}%")
    else:
        lines.append("No significant latch wait activity or view inaccessible.")

    # 2. Buffer Pool Summary
    lines.append("\n" + "-" * 80)
    lines.append("2. BUFFER POOL SIZING AND HIT RATIO SUMMARY")
    lines.append("-" * 80)
    if report.buffer_pool_summary:
        lines.append(f"{'Pool Name':<12} {'Blk Size':>8} {'Size MB':>10} {'Phys Reads':>12} {'DB Blk Gets':>12} {'Cons Gets':>12} {'Hit Ratio %':>11}")
        lines.append("-" * 83)
        for pool in report.buffer_pool_summary:
            lines.append(f"{pool.pool_name:<12} {pool.block_size_bytes:>8d} {pool.size_mb:>10.2f} {pool.physical_reads:>12d} {pool.db_block_gets:>12d} {pool.consistent_gets:>12d} {pool.hit_ratio_pct:>10.2f}%")
    else:
        lines.append("No buffer pool statistics available.")

    # 3. Buffer Busy Waits
    lines.append("\n" + "-" * 80)
    lines.append("3. BUFFER BUSY WAITS AND WAITSTAT ANALYSIS")
    lines.append("-" * 80)
    if report.buffer_busy_waits:
        lines.append("Block Class Wait Statistics (V$WAITSTAT):")
        if report.buffer_busy_waits.wait_stats:
            lines.append(f"{'Block Class':<24} {'Wait Count':>12} {'Time Waited (ms)':>18}")
            lines.append("-" * 56)
            for ws in report.buffer_busy_waits.wait_stats:
                lines.append(f"{ws.class_name:<24} {ws.count:>12d} {ws.time_waited_ms:>18.2f}")
        else:
            lines.append("  No wait statistics recorded in V$WAITSTAT.")

        lines.append("\nRelated System Wait Events (V$SYSTEM_EVENT):")
        if report.buffer_busy_waits.system_events:
            lines.append(f"{'Event Name':<28} {'Total Waits':>12} {'Time Waited (ms)':>18} {'Avg Wait (ms)':>14}")
            lines.append("-" * 74)
            for ev in report.buffer_busy_waits.system_events:
                lines.append(f"{ev.event_name:<28} {ev.total_waits:>12d} {ev.time_waited_ms:>18.2f} {ev.avg_wait_ms:>14.2f}")
        else:
            lines.append("  No related system wait events recorded.")

        lines.append("\nRoot-Cause Tuning Recommendations:")
        for rec in report.buffer_busy_waits.tuning_recommendations:
            lines.append(f"  * {rec}")
    else:
        lines.append("No buffer busy wait analysis available.")

    # 4. Locked Objects and Blocking Lock Hierarchy
    lines.append("\n" + "-" * 80)
    lines.append("4. LOCKED OBJECTS AND BLOCKING LOCK HIERARCHY")
    lines.append("-" * 80)
    if report.locked_objects_report:
        lines.append("Locked Objects:")
        if report.locked_objects_report.locked_objects:
            lines.append(f"{'SID':>5} {'User':<12} {'Owner':<12} {'Object Name':<20} {'Type':<10} {'Mode Held':<16} {'Blocking SID':>12}")
            lines.append("-" * 83)
            for lo in report.locked_objects_report.locked_objects:
                user = lo.username or "N/A"
                blocking = str(lo.blocking_sid) if lo.blocking_sid else "None"
                lines.append(f"{lo.sid:>5d} {user:<12} {lo.object_owner:<12} {lo.object_name:<20} {lo.object_type:<10} {lo.lock_mode_held:<16} {blocking:>12}")
        else:
            lines.append("  No active object locks found.")

        lines.append("\nBlocking Lock Hierarchy Summary:")
        if report.locked_objects_report.root_blockers:
            lines.append(f"  Root Blocker SIDs: {', '.join(str(s) for s in report.locked_objects_report.root_blockers)}")
            node_map = {n.sid: n for n in report.locked_objects_report.blocking_chains}
            for root_sid in report.locked_objects_report.root_blockers:
                root_node = node_map.get(root_sid)
                user = root_node.username if root_node and root_node.username else "N/A"
                prog = root_node.program if root_node and root_node.program else "N/A"
                sql = root_node.sql_id if root_node and root_node.sql_id else "N/A"
                lines.append(f"  [+] Blocker SID {root_sid} (User: {user}, Program: {prog}, SQL_ID: {sql})")
                if root_node and root_node.blocked_sids:
                    for blocked_sid in root_node.blocked_sids:
                        b_node = node_map.get(blocked_sid)
                        b_user = b_node.username if b_node and b_node.username else "N/A"
                        b_wait = f"{b_node.wait_seconds}s" if b_node and b_node.wait_seconds is not None else "N/A"
                        lines.append(f"      └── Blocks SID {blocked_sid} (User: {b_user}, Wait: {b_wait})")
        else:
            lines.append("  No active blocking lock sessions detected.")
    else:
        lines.append("No locked objects report available.")

    lines.append("\n" + "=" * 80)
    lines.append("END OF DIAGNOSTICS REPORT")
    lines.append("=" * 80)

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for performance diagnostics analyzer.

    Returns:
        argparse.ArgumentParser: Configured argument parser.
    """
    parser = argparse.ArgumentParser(description="Oracle database performance diagnostics analyzer.")
    parser.add_argument(
        "-u",
        "--user",
        default=os.getenv("ORACLE_USER"),
        help="Database username (default: ORACLE_USER)",
    )
    parser.add_argument(
        "-p",
        "--password",
        default=os.getenv("ORACLE_PASSWORD"),
        help="Database password (default: ORACLE_PASSWORD)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("ORACLE_HOST", "localhost"),
        help="Oracle database host (default: ORACLE_HOST or localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ORACLE_PORT", "1521")),
        help="Oracle database port (default: ORACLE_PORT or 1521)",
    )
    parser.add_argument(
        "--service-name",
        default=os.getenv("ORACLE_SERVICE_NAME"),
        help="Oracle service name (default: ORACLE_SERVICE_NAME)",
    )
    parser.add_argument(
        "--sid",
        default=os.getenv("ORACLE_SID"),
        help="Oracle SID (default: ORACLE_SID)",
    )
    parser.add_argument(
        "--sysdba",
        action="store_true",
        help="Connect with SYSDBA privilege",
    )
    parser.add_argument(
        "--analyzer",
        choices=[
            "latch_summary",
            "buffer_pool",
            "buffer_busy_waits",
            "locked_objects",
            "all",
        ],
        default="all",
        help="Select analyzer module to run (default: all)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Top N rows to return for ranked metrics (default: 20)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output report format (default: text)",
    )
    parser.add_argument(
        "-o",
        "--output",
        "--output-file",
        dest="output_file",
        help="File path to save the output report",
    )
    return parser


def main() -> int:
    """CLI execution entrypoint.

    Returns:
        int: Exit status code.
    """
    parser = build_parser()
    args = parser.parse_args()

    if not args.user:
        logger.error("Database username must be specified via -u/--user or ORACLE_USER")
        return 1
    if not args.password:
        logger.error("Database password must be specified via -p/--password or ORACLE_PASSWORD")
        return 1
    if not args.service_name and not args.sid:
        logger.error("Either --service-name or --sid must be specified (or via environment variables)")
        return 1

    try:
        config = OracleConnectionConfig(
            hostname=args.host,
            port=args.port,
            service_name=args.service_name,
            sid=args.sid,
            username=args.user,
            password=SecretStr(args.password),
            is_sysdba=args.sysdba,
        )
    except ValidationError as exc:
        logger.error("Configuration validation failed: {}", exc)
        return 1

    driver = OracleDriver(config)
    analyzer = OraclePerformanceAnalyzer(driver=driver, top_n=args.top)

    try:
        if args.analyzer == "all":
            report = analyzer.run_all()
        else:
            report = PerformanceDiagnosticsReport()
            if args.analyzer == "latch_summary":
                report.latch_summary = analyzer.analyze_latch_summary()
            elif args.analyzer == "buffer_pool":
                report.buffer_pool_summary = analyzer.analyze_buffer_pool()
            elif args.analyzer == "buffer_busy_waits":
                report.buffer_busy_waits = analyzer.analyze_buffer_busy_waits()
            elif args.analyzer == "locked_objects":
                report.locked_objects_report = analyzer.analyze_locked_objects()
    except oracledb.DatabaseError as exc:
        logger.error("Database error during performance diagnostic collection: {}", exc)
        return 1

    if args.format == "json":
        output_text = report.model_dump_json(indent=2)
    else:
        output_text = format_performance_report_text(report)

    if args.output_file:
        try:
            with open(args.output_file, "w", encoding="utf-8") as f:
                f.write(output_text)
            logger.info("Diagnostics report saved to {}", args.output_file)
        except OSError as exc:
            logger.error("Failed to write report to {}: {}", args.output_file, exc)
            return 1
    else:
        sys.stdout.write(output_text + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
