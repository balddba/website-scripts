"""Unit tests for Oracle performance diagnostics analyzer script."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import oracledb
import pytest
from pydantic import SecretStr, ValidationError

from oracle.python.oracle_performance_diagnostics import (
    BlockingHierarchyNode,
    BufferBusyWaitAnalysis,
    BufferPoolSummary,
    LatchWaitMetric,
    LockedObjectDetail,
    LockedObjectsReport,
    OracleConnectionConfig,
    OracleDriver,
    OraclePerformanceAnalyzer,
    PerformanceDiagnosticsReport,
    WaitEventStat,
    WaitStatMetric,
    build_parser,
    format_performance_report_text,
    get_lock_mode_name,
    main,
)


def test_get_lock_mode_name() -> None:
    """Test lock mode translation from integer codes to readable descriptions."""
    assert get_lock_mode_name(0) == "None (0)"
    assert get_lock_mode_name(1) == "Null (1)"
    assert get_lock_mode_name(2) == "Row-S / SS (2)"
    assert get_lock_mode_name(3) == "Row-X / SX (3)"
    assert get_lock_mode_name(4) == "Share / S (4)"
    assert get_lock_mode_name(5) == "S/Row-X / SSX (5)"
    assert get_lock_mode_name(6) == "Exclusive / X (6)"
    assert get_lock_mode_name(None) == "None (0)"
    assert get_lock_mode_name(99) == "Unknown (99)"


def test_oracle_connection_config_valid() -> None:
    """Test valid connection configuration parsing."""
    config = OracleConnectionConfig(
        hostname="dbhost.example.com",
        port=1521,
        service_name="ORCLPDB1",
        username="SYSTEM",
        password=SecretStr("secret_pwd"),
        is_sysdba=True,
    )
    assert config.hostname == "dbhost.example.com"
    assert config.port == 1521
    assert config.service_name == "ORCLPDB1"
    assert config.sid is None
    assert config.username == "SYSTEM"
    assert config.password.get_secret_value() == "secret_pwd"
    assert "secret_pwd" not in repr(config.password)
    assert config.is_sysdba is True


def test_oracle_connection_config_extra_forbidden() -> None:
    """Test that unexpected config attributes trigger validation errors."""
    with pytest.raises(ValidationError):
        OracleConnectionConfig(
            username="user",
            password=SecretStr("pwd"),
            service_name="svc",
            invalid_param="forbidden",  # type: ignore[call-arg]
        )


def test_oracle_driver_session_connect_service() -> None:
    """Test driver creates DSN with service_name."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        service_name="MYSERVICE",
        username="SCOTT",
        password=SecretStr("TIGER"),
    )
    driver = OracleDriver(config)
    mock_conn = MagicMock(spec=oracledb.Connection)

    with (
        patch("oracledb.makedsn", return_value="DSN_SERVICE") as mock_makedsn,
        patch("oracledb.connect", return_value=mock_conn) as mock_connect,
    ):
        with driver.session() as conn:
            assert conn == mock_conn

        mock_makedsn.assert_called_once_with("db.test", 1521, service_name="MYSERVICE")
        mock_connect.assert_called_once_with(
            user="SCOTT",
            password="TIGER",
            dsn="DSN_SERVICE",
            mode=0,
        )
        mock_conn.close.assert_called_once()


def test_oracle_driver_session_connect_sid() -> None:
    """Test driver creates DSN with sid."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        sid="ORCL",
        username="SYS",
        password=SecretStr("CHANGE_ON_INSTALL"),
    )
    driver = OracleDriver(config)
    mock_conn = MagicMock(spec=oracledb.Connection)

    with (
        patch("oracledb.makedsn", return_value="DSN_SID") as mock_makedsn,
        patch("oracledb.connect", return_value=mock_conn) as mock_connect,
    ):
        with driver.session() as conn:
            assert conn == mock_conn

        mock_makedsn.assert_called_once_with("db.test", 1521, sid="ORCL")
        mock_connect.assert_called_once_with(
            user="SYS",
            password="CHANGE_ON_INSTALL",
            dsn="DSN_SID",
            mode=oracledb.SYSDBA,
        )


def test_oracle_driver_session_connect_fallback_dsn() -> None:
    """Test driver creates host:port string when neither service nor sid is given."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        username="USER",
        password=SecretStr("PWD"),
    )
    driver = OracleDriver(config)
    mock_conn = MagicMock(spec=oracledb.Connection)

    with patch("oracledb.connect", return_value=mock_conn) as mock_connect:
        with driver.session() as conn:
            assert conn == mock_conn
        mock_connect.assert_called_once_with(
            user="USER",
            password="PWD",
            dsn="db.test:1521",
            mode=0,
        )


def test_oracle_driver_session_connect_error() -> None:
    """Test driver handles connection failure and re-raises exception."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        service_name="SVC",
        username="SCOTT",
        password=SecretStr("TIGER"),
    )
    driver = OracleDriver(config)

    with (
        patch("oracledb.connect", side_effect=oracledb.DatabaseError("ORA-12541")),
        pytest.raises(oracledb.DatabaseError),
        driver.session(),
    ):
        pass


def test_oracle_driver_session_close_error() -> None:
    """Test driver handles error during connection close gracefully."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        service_name="SVC",
        username="SCOTT",
        password=SecretStr("TIGER"),
    )
    driver = OracleDriver(config)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_conn.close.side_effect = oracledb.DatabaseError("Close error")

    with patch("oracledb.connect", return_value=mock_conn):
        with driver.session() as conn:
            assert conn == mock_conn
        mock_conn.close.assert_called_once()


def test_analyze_latch_summary() -> None:
    """Test latch wait summary analysis query and parsing."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session

    mock_cursor.fetchall.return_value = [
        (
            "cache buffers chains",
            5000000,
            12000,
            450,
            1000,
            50,
            1520.5,
            99.76,
        ),
        (
            "row cache objects",
            1000000,
            500,
            10,
            200,
            0,
            85.2,
            99.95,
        ),
    ]

    analyzer = OraclePerformanceAnalyzer(driver=mock_driver, top_n=10)
    latches = analyzer.analyze_latch_summary()

    assert len(latches) == 2
    assert latches[0].name == "cache buffers chains"
    assert latches[0].gets == 5000000
    assert latches[0].misses == 12000
    assert latches[0].sleeps == 450
    assert latches[0].immediate_gets == 1000
    assert latches[0].immediate_misses == 50
    assert latches[0].wait_time_ms == 1520.5
    assert latches[0].hit_ratio_pct == 99.76

    assert latches[1].name == "row cache objects"
    assert latches[1].hit_ratio_pct == 99.95


def test_analyze_latch_summary_ora_00942() -> None:
    """Test latch wait summary falls back to empty list on ORA-00942."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session
    mock_cursor.execute.side_effect = oracledb.DatabaseError("ORA-00942: table or view does not exist")

    analyzer = OraclePerformanceAnalyzer(driver=mock_driver)
    results = analyzer.analyze_latch_summary()
    assert results == []


def test_analyze_latch_summary_error_reraised() -> None:
    """Test non-00942 DatabaseError is re-raised."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session
    mock_cursor.execute.side_effect = oracledb.DatabaseError("ORA-01017: invalid user")

    analyzer = OraclePerformanceAnalyzer(driver=mock_driver)
    with pytest.raises(oracledb.DatabaseError):
        analyzer.analyze_latch_summary()


def test_analyze_buffer_pool() -> None:
    """Test buffer pool summary analysis and metrics calculation."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session

    mock_cursor.fetchall.return_value = [
        ("DEFAULT", 8192, 512.0, 15000, 200000, 1800000, 4500, 0, 0, 99.25),
        ("KEEP", 8192, 128.0, 200, 5000, 45000, 50, 0, 0, 99.60),
    ]

    analyzer = OraclePerformanceAnalyzer(driver=mock_driver)
    pools = analyzer.analyze_buffer_pool()

    assert len(pools) == 2
    assert pools[0].pool_name == "DEFAULT"
    assert pools[0].block_size_bytes == 8192
    assert pools[0].size_mb == 512.0
    assert pools[0].physical_reads == 15000
    assert pools[0].db_block_gets == 200000
    assert pools[0].consistent_gets == 1800000
    assert pools[0].physical_writes == 4500
    assert pools[0].free_buffer_waits == 0
    assert pools[0].write_complete_waits == 0
    assert pools[0].hit_ratio_pct == 99.25


def test_analyze_buffer_pool_ora_00942() -> None:
    """Test buffer pool analysis handles ORA-00942 gracefully."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session
    mock_cursor.execute.side_effect = oracledb.DatabaseError("ORA-00942: table or view does not exist")

    analyzer = OraclePerformanceAnalyzer(driver=mock_driver)
    results = analyzer.analyze_buffer_pool()
    assert results == []


def test_analyze_buffer_pool_error_reraised() -> None:
    """Test buffer pool analysis re-raises generic database errors."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session
    mock_cursor.execute.side_effect = oracledb.DatabaseError("ORA-03113: end of file")

    analyzer = OraclePerformanceAnalyzer(driver=mock_driver)
    with pytest.raises(oracledb.DatabaseError):
        analyzer.analyze_buffer_pool()


def test_analyze_buffer_busy_waits_with_suggestions() -> None:
    """Test buffer busy wait analysis and specific root-cause suggestion generation."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session

    mock_cursor.fetchall.side_effect = [
        # V$WAITSTAT
        [
            ("data block", 1500, 4500.0),
            ("segment header", 350, 1200.0),
            ("undo header", 80, 240.0),
            ("undo block", 45, 110.0),
            ("free list", 30, 95.0),
        ],
        # V$SYSTEM_EVENT
        [
            ("buffer busy waits", 2005, 6145.0, 3.06),
            ("read by other session", 850, 4200.0, 4.94),
            ("write complete waits", 120, 800.0, 6.67),
        ],
    ]

    analyzer = OraclePerformanceAnalyzer(driver=mock_driver)
    analysis = analyzer.analyze_buffer_busy_waits()

    assert len(analysis.wait_stats) == 5
    assert len(analysis.system_events) == 3
    assert len(analysis.tuning_recommendations) >= 6

    recs_joined = "\n".join(analysis.tuning_recommendations)
    assert "Data Block Contention" in recs_joined
    assert "Segment Header Contention" in recs_joined
    assert "Undo Header Contention" in recs_joined
    assert "Undo Block Contention" in recs_joined
    assert "Free List Contention" in recs_joined
    assert "Read By Other Session Contention" in recs_joined
    assert "DBWR / Checkpoint Latency" in recs_joined
    assert "Sequence Caching" in recs_joined


def test_analyze_buffer_busy_waits_empty() -> None:
    """Test buffer busy wait analysis with no active waits."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session
    mock_cursor.fetchall.side_effect = [[], []]

    analyzer = OraclePerformanceAnalyzer(driver=mock_driver)
    analysis = analyzer.analyze_buffer_busy_waits()

    assert analysis.wait_stats == []
    assert analysis.system_events == []
    assert len(analysis.tuning_recommendations) == 1
    assert "No significant buffer busy wait bottlenecks" in analysis.tuning_recommendations[0]


def test_analyze_buffer_busy_waits_ora_00942() -> None:
    """Test buffer busy wait views fallback on ORA-00942."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session
    mock_cursor.execute.side_effect = oracledb.DatabaseError("ORA-00942: table or view does not exist")

    analyzer = OraclePerformanceAnalyzer(driver=mock_driver)
    analysis = analyzer.analyze_buffer_busy_waits()
    assert analysis.wait_stats == []
    assert analysis.system_events == []


def test_analyze_locked_objects_and_hierarchy() -> None:
    """Test locked objects extraction and blocking lock tree hierarchy construction."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session

    # 1. Locked objects rows
    locked_rows = [
        (
            101,  # sid
            1234,  # serial#
            "APPUSER",  # username
            "oracle",  # osuser
            "app01.prod",  # machine
            "sqlplus@app01",  # program
            "SCOTT",  # object_owner
            "ORDERS",  # object_name
            "TABLE",  # object_type
            3,  # lock_mode_held (Row-X)
            0,  # lock_mode_requested
            None,  # blocking_sid
            0,  # wait_seconds
            "sql123",  # sql_id
        ),
        (
            102,
            5678,
            "BATCHUSER",
            "batch",
            "batch01.prod",
            "batch_job.py",
            "SCOTT",
            "ORDERS",
            "TABLE",
            0,
            6,  # lock_mode_requested (Exclusive)
            101,  # blocking_sid
            45,
            "sql456",
        ),
    ]

    # 2. V$SESSION hierarchy rows
    session_rows = [
        (101, 1234, "APPUSER", "sqlplus@app01", "sql123", 0, None),
        (102, 5678, "BATCHUSER", "batch_job.py", "sql456", 45, 101),
    ]

    mock_cursor.fetchall.side_effect = [locked_rows, session_rows]

    analyzer = OraclePerformanceAnalyzer(driver=mock_driver)
    report = analyzer.analyze_locked_objects()

    assert len(report.locked_objects) == 2
    assert report.locked_objects[0].sid == 101
    assert report.locked_objects[0].lock_mode_held == "Row-X / SX (3)"
    assert report.locked_objects[1].sid == 102
    assert report.locked_objects[1].lock_mode_requested == "Exclusive / X (6)"
    assert report.locked_objects[1].blocking_sid == 101

    assert report.root_blockers == [101]
    assert len(report.blocking_chains) == 2

    node_101 = next(n for n in report.blocking_chains if n.sid == 101)
    assert node_101.blocked_sids == [102]


def test_analyze_locked_objects_dba_fallback_to_all_objects() -> None:
    """Test fallback from DBA_OBJECTS to ALL_OBJECTS on ORA-00942."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session

    call_count = 0

    def mock_execute(sql: str, *args, **kwargs) -> None:
        nonlocal call_count
        call_count += 1
        if "dba_objects" in sql:
            raise oracledb.DatabaseError("ORA-00942: table or view does not exist")

    mock_cursor.execute.side_effect = mock_execute
    mock_cursor.fetchall.side_effect = [
        [
            (
                201,
                111,
                "DEV",
                "devuser",
                "laptop",
                "app",
                "HR",
                "EMPLOYEES",
                "TABLE",
                3,
                0,
                None,
                0,
                "sql999",
            )
        ],
        [],
    ]

    analyzer = OraclePerformanceAnalyzer(driver=mock_driver)
    report = analyzer.analyze_locked_objects()

    assert len(report.locked_objects) == 1
    assert report.locked_objects[0].object_name == "EMPLOYEES"


def test_analyze_locked_objects_all_views_ora_00942() -> None:
    """Test locked objects returns empty report if all views fail with ORA-00942."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session
    mock_cursor.execute.side_effect = oracledb.DatabaseError("ORA-00942: table or view does not exist")

    analyzer = OraclePerformanceAnalyzer(driver=mock_driver)
    report = analyzer.analyze_locked_objects()
    assert report.locked_objects == []
    assert report.blocking_chains == []
    assert report.root_blockers == []


def test_run_all_consolidation() -> None:
    """Test running all analyzers together."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session

    # Order of fetchall calls:
    # 1. Latch summary
    # 2. Buffer pool
    # 3. Buffer busy waitstat
    # 4. Buffer busy system_event
    # 5. Locked objects
    # 6. Session hierarchy
    mock_cursor.fetchall.side_effect = [
        [("latch1", 100, 2, 0, 0, 0, 1.5, 98.0)],
        [("DEFAULT", 8192, 100.0, 50, 1000, 9000, 10, 0, 0, 99.5)],
        [("data block", 10, 50.0)],
        [("buffer busy waits", 10, 50.0, 5.0)],
        [],
        [],
    ]

    analyzer = OraclePerformanceAnalyzer(driver=mock_driver)
    report = analyzer.run_all()

    assert len(report.latch_summary) == 1
    assert len(report.buffer_pool_summary) == 1
    assert report.buffer_busy_waits is not None
    assert len(report.buffer_busy_waits.wait_stats) == 1
    assert report.locked_objects_report is not None


def test_format_performance_report_text() -> None:
    """Test text report formatting output contains all sections and formatted tables."""
    report = PerformanceDiagnosticsReport(
        timestamp=datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc),
        latch_summary=[
            LatchWaitMetric(
                name="cache buffers chains",
                gets=100000,
                misses=500,
                sleeps=20,
                immediate_gets=50,
                immediate_misses=2,
                wait_time_ms=120.5,
                hit_ratio_pct=99.5,
            )
        ],
        buffer_pool_summary=[
            BufferPoolSummary(
                pool_name="DEFAULT",
                block_size_bytes=8192,
                size_mb=256.0,
                physical_reads=1000,
                db_block_gets=50000,
                consistent_gets=450000,
                physical_writes=200,
                free_buffer_waits=0,
                write_complete_waits=0,
                hit_ratio_pct=99.8,
            )
        ],
        buffer_busy_waits=BufferBusyWaitAnalysis(
            wait_stats=[WaitStatMetric(class_name="data block", count=150, time_waited_ms=450.0)],
            system_events=[
                WaitEventStat(
                    event_name="buffer busy waits",
                    total_waits=150,
                    time_waited_ms=450.0,
                    avg_wait_ms=3.0,
                )
            ],
            tuning_recommendations=["Data Block Contention recommendation"],
        ),
        locked_objects_report=LockedObjectsReport(
            locked_objects=[
                LockedObjectDetail(
                    sid=10,
                    serial_number=1,
                    username="APPUSER",
                    object_owner="SCOTT",
                    object_name="ORDERS",
                    object_type="TABLE",
                    lock_mode_held_code=3,
                    lock_mode_held="Row-X / SX (3)",
                    lock_mode_requested_code=0,
                    lock_mode_requested="None (0)",
                    blocking_sid=None,
                    wait_seconds=0,
                    current_sql_id="abc123",
                )
            ],
            blocking_chains=[
                BlockingHierarchyNode(
                    sid=10,
                    serial_number=1,
                    username="APPUSER",
                    program="app.py",
                    sql_id="abc123",
                    wait_seconds=0,
                    blocked_sids=[20],
                ),
                BlockingHierarchyNode(
                    sid=20,
                    serial_number=2,
                    username="WAITUSER",
                    program="wait.py",
                    sql_id="xyz789",
                    wait_seconds=30,
                    blocked_sids=[],
                ),
            ],
            root_blockers=[10],
        ),
    )

    text = format_performance_report_text(report)
    assert "ORACLE PERFORMANCE DIAGNOSTICS REPORT" in text
    assert "1. LATCH WAIT AND CONTENTION SUMMARY" in text
    assert "cache buffers chains" in text
    assert "2. BUFFER POOL SIZING AND HIT RATIO SUMMARY" in text
    assert "DEFAULT" in text
    assert "3. BUFFER BUSY WAITS AND WAITSTAT ANALYSIS" in text
    assert "data block" in text
    assert "Data Block Contention recommendation" in text
    assert "4. LOCKED OBJECTS AND BLOCKING LOCK HIERARCHY" in text
    assert "Root Blocker SIDs: 10" in text
    assert "Blocks SID 20" in text


def test_format_performance_report_empty() -> None:
    """Test text report formatting when all sections are empty."""
    report = PerformanceDiagnosticsReport(
        timestamp=datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc),
    )
    text = format_performance_report_text(report)
    assert "No significant latch wait activity or view inaccessible." in text
    assert "No buffer pool statistics available." in text
    assert "No buffer busy wait analysis available." in text
    assert "No locked objects report available." in text


def test_build_parser() -> None:
    """Test build_parser CLI argument definitions and default values."""
    parser = build_parser()
    args = parser.parse_args(["-u", "SCOTT", "-p", "TIGER", "--sid", "ORCL"])
    assert args.user == "SCOTT"
    assert args.password == "TIGER"
    assert args.sid == "ORCL"
    assert args.analyzer == "all"
    assert args.top == 20
    assert args.format == "text"


def test_cli_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI returns error code 1 when credentials are missing."""
    monkeypatch.delenv("ORACLE_USER", raising=False)
    monkeypatch.delenv("ORACLE_PASSWORD", raising=False)
    monkeypatch.delenv("ORACLE_SERVICE_NAME", raising=False)
    monkeypatch.delenv("ORACLE_SID", raising=False)

    with patch("sys.argv", ["oracle_performance_diagnostics.py"]):
        assert main() == 1

    with patch(
        "sys.argv",
        ["oracle_performance_diagnostics.py", "-u", "SCOTT"],
    ):
        assert main() == 1

    with patch(
        "sys.argv",
        ["oracle_performance_diagnostics.py", "-u", "SCOTT", "-p", "TIGER"],
    ):
        assert main() == 1


def test_cli_validation_failure() -> None:
    """Test CLI returns error code 1 on config validation errors."""
    with (
        patch(
            "sys.argv",
            [
                "oracle_performance_diagnostics.py",
                "-u",
                "SCOTT",
                "-p",
                "TIGER",
                "--service-name",
                "SVC",
                "--port",
                "not_an_int",
            ],
        ),
        pytest.raises(SystemExit),
    ):
        main()


def test_cli_execution_all_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test full CLI execution running all analyzers with text output to file."""
    output_file = tmp_path / "diagnostics.txt"
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    with (
        patch("oracledb.connect", return_value=mock_conn),
        patch(
            "sys.argv",
            [
                "oracle_performance_diagnostics.py",
                "-u",
                "SCOTT",
                "-p",
                "TIGER",
                "--service-name",
                "SVC",
                "--analyzer",
                "all",
                "--top",
                "15",
                "-o",
                str(output_file),
            ],
        ),
    ):
        assert main() == 0
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "ORACLE PERFORMANCE DIAGNOSTICS REPORT" in content


def test_cli_execution_individual_analyzer_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI execution for individual analyzer producing JSON to stdout."""
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    for analyzer_name in [
        "latch_summary",
        "buffer_pool",
        "buffer_busy_waits",
        "locked_objects",
    ]:
        with (
            patch("oracledb.connect", return_value=mock_conn),
            patch(
                "sys.argv",
                [
                    "oracle_performance_diagnostics.py",
                    "-u",
                    "SCOTT",
                    "-p",
                    "TIGER",
                    "--sid",
                    "ORCL",
                    "--analyzer",
                    analyzer_name,
                    "--format",
                    "json",
                ],
            ),
        ):
            assert main() == 0
            captured = capsys.readouterr().out
            assert "{" in captured
            assert "}" in captured


def test_cli_database_error_exit() -> None:
    """Test CLI handles DatabaseError during analyzer execution with exit code 1."""
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.execute.side_effect = oracledb.DatabaseError("ORA-01017: invalid user")

    with (
        patch("oracledb.connect", return_value=mock_conn),
        patch(
            "sys.argv",
            [
                "oracle_performance_diagnostics.py",
                "-u",
                "SCOTT",
                "-p",
                "TIGER",
                "--service-name",
                "SVC",
            ],
        ),
    ):
        assert main() == 1


def test_cli_output_file_oserror(tmp_path: Path) -> None:
    """Test CLI handles OSError writing output file with exit code 1."""
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    # Invalid directory path to trigger OSError
    invalid_path = tmp_path / "nonexistent_dir" / "sub" / "report.txt"

    with (
        patch("oracledb.connect", return_value=mock_conn),
        patch(
            "sys.argv",
            [
                "oracle_performance_diagnostics.py",
                "-u",
                "SCOTT",
                "-p",
                "TIGER",
                "--service-name",
                "SVC",
                "-o",
                str(invalid_path),
            ],
        ),
    ):
        assert main() == 1
