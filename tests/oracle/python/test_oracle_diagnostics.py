"""Unit tests for Oracle diagnostic and performance analyzer script."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import oracledb
import pytest
from pydantic import SecretStr, ValidationError

from oracle.python.oracle_diagnostics import (
    DiagnosticsReport,
    HistogramInfo,
    LobSegmentInfo,
    OracleConnectionConfig,
    OracleDiagnosticsAnalyzer,
    OracleDriver,
    RedoLogInfo,
    TablePartitionInfo,
    WaitEventMetric,
    format_report_text,
    main,
)


def test_oracle_connection_config_valid() -> None:
    """Test valid configuration instantiation and field parsing."""
    config = OracleConnectionConfig(
        hostname="dbhost.example.com",
        port=1521,
        service_name="ORCLPDB1",
        username="SYSTEM",
        password=SecretStr("secret_pwd"),
        is_sysdba=True,
        owner="SCOTT",
        table_name="EMP",
        tablespace_name="USERS",
    )
    assert config.hostname == "dbhost.example.com"
    assert config.port == 1521
    assert config.service_name == "ORCLPDB1"
    assert config.username == "SYSTEM"
    assert config.password.get_secret_value() == "secret_pwd"
    assert "secret_pwd" not in repr(config.password)
    assert config.is_sysdba is True
    assert config.owner == "SCOTT"
    assert config.table_name == "EMP"
    assert config.tablespace_name == "USERS"


def test_oracle_connection_config_extra_forbidden() -> None:
    """Test that extra configuration parameters are strictly rejected."""
    with pytest.raises(ValidationError):
        OracleConnectionConfig(
            username="user",
            password=SecretStr("pwd"),
            service_name="svc",
            extra_arg="invalid",  # type: ignore[call-arg]
        )


def test_oracle_driver_session_connect() -> None:
    """Test driver session opens connection using DSN."""
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
        patch("oracledb.makedsn", return_value="DSN_STRING") as mock_makedsn,
        patch("oracledb.connect") as mock_connect,
    ):
        mock_connect.return_value.__enter__.return_value = mock_conn
        with driver.session() as conn:
            assert conn == mock_conn

        mock_makedsn.assert_called_once_with("db.test", 1521, service_name="MYSERVICE")
        mock_connect.assert_called_once_with(
            user="SCOTT",
            password="TIGER",
            dsn="DSN_STRING",
            mode=0,
        )


def test_analyze_sequential_reads() -> None:
    """Test analyzing db file sequential read wait statistics."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
        ("db file sequential read", 5000, 0, 150000.5, 30.0),
        ("db file scattered read", 1200, 0, 60000.0, 50.0),
    ]

    analyzer = OracleDiagnosticsAnalyzer(mock_driver)
    results = analyzer.analyze_sequential_reads(mock_conn)

    assert len(results) == 2
    assert results[0].event_name == "db file sequential read"
    assert results[0].total_waits == 5000
    assert results[0].avg_wait_ms == 30.0


def test_analyze_log_file_syncs() -> None:
    """Test analyzing log file sync wait events."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
        ("log file sync", 1000, 0, 12000.0, 12.0),
        ("log file parallel write", 950, 0, 8000.0, 8.42),
    ]

    analyzer = OracleDiagnosticsAnalyzer(mock_driver)
    results = analyzer.analyze_log_file_syncs(mock_conn)

    assert len(results) == 2
    assert results[0].event_name == "log file sync"
    assert results[0].total_waits == 1000
    assert results[0].avg_wait_ms == 12.0


def test_analyze_buffer_queue_stats() -> None:
    """Test analyzing dirty buffer queue and DBWR inspection statistics."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
        ("dirty buffers inspected", 125),
        ("free buffer waits", 2),
    ]

    analyzer = OracleDiagnosticsAnalyzer(mock_driver)
    results = analyzer.analyze_buffer_queue_stats(mock_conn)

    assert len(results) == 2
    assert results[0].name == "dirty buffers inspected"
    assert results[0].value == 125


def test_analyze_background_processes() -> None:
    """Test querying background processes information."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
        (
            "DBW0",
            "db writer process 0",
            "1234",
            10,
            1,
            "ACTIVE",
            "rdbms ipc message",
            "WAITING",
        ),
        (
            "LGWR",
            "redo log writer",
            "1235",
            11,
            1,
            "ACTIVE",
            "rdbms ipc message",
            "WAITING",
        ),
    ]

    analyzer = OracleDiagnosticsAnalyzer(mock_driver)
    results = analyzer.analyze_background_processes(mock_conn)

    assert len(results) == 2
    assert results[0].process_name == "DBW0"
    assert results[0].os_pid == "1234"
    assert results[1].process_name == "LGWR"


def test_analyze_user_quotas() -> None:
    """Test tablespace quota inspection and limit parsing."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
        ("SCOTT", "USERS", 10485760, 52428800, 1280, 6400),
        ("HR", "USERS", 2097152, -1, 256, -1),
    ]

    analyzer = OracleDiagnosticsAnalyzer(mock_driver, owner="SCOTT")
    results = analyzer.analyze_user_quotas(mock_conn)

    assert len(results) == 2
    assert results[0].username == "SCOTT"
    assert results[0].bytes_used == 10485760
    assert results[0].max_bytes == 52428800
    assert results[0].is_unlimited is False
    assert results[1].is_unlimited is True


def test_analyze_buffer_pool_stats() -> None:
    """Test buffer pool sizing and performance metrics collection."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
        ("DEFAULT", 8192, 10000, 50000, 12000, 0, 4),
    ]

    analyzer = OracleDiagnosticsAnalyzer(mock_driver)
    results = analyzer.analyze_buffer_pool_stats(mock_conn)

    assert len(results) == 1
    assert results[0].pool_name == "DEFAULT"
    assert results[0].block_size_bytes == 8192
    assert results[0].physical_reads == 50000


def test_analyze_index_stats() -> None:
    """Test index statistics analysis."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    mock_cursor.fetchall.return_value = [
        ("SCOTT", "PK_EMP", "EMP", "NORMAL", "UNIQUE", "VALID", 1, 10, 14, 1, 14, now),
    ]

    analyzer = OracleDiagnosticsAnalyzer(mock_driver, owner="SCOTT", table_name="EMP")
    results = analyzer.analyze_index_stats(mock_conn)

    assert len(results) == 1
    assert results[0].index_name == "PK_EMP"
    assert results[0].b_level == 1
    assert results[0].leaf_blocks == 10
    assert results[0].clustering_factor == 1


def test_analyze_column_stats() -> None:
    """Test table column data types and distinct count inspection."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
        ("SCOTT", "EMP", "EMPNO", "NUMBER(4,0)", "N", 14, 0.0714, 0, "NONE", 4),
        ("SCOTT", "EMP", "ENAME", "VARCHAR2(10)", "Y", 14, 0.0714, 0, "NONE", 6),
    ]

    analyzer = OracleDiagnosticsAnalyzer(mock_driver, owner="SCOTT", table_name="EMP")
    results = analyzer.analyze_column_stats(mock_conn)

    assert len(results) == 2
    assert results[0].column_name == "EMPNO"
    assert results[0].num_distinct == 14
    assert results[0].density == 0.0714


def test_analyze_table_storage() -> None:
    """Test table storage, block counts, and segment size analysis."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    mock_cursor.fetchall.return_value = [
        ("SCOTT", "EMP", "USERS", 14, 5, 1, 8000, 0, 36, now, 65536, 1),
    ]

    analyzer = OracleDiagnosticsAnalyzer(mock_driver, owner="SCOTT", table_name="EMP")
    results = analyzer.analyze_table_storage(mock_conn)

    assert len(results) == 1
    assert results[0].table_name == "EMP"
    assert results[0].tablespace_name == "USERS"
    assert results[0].blocks == 5
    assert results[0].segment_bytes == 65536


def test_analyze_partitions() -> None:
    """Test table partition metadata and block inspection."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    mock_cursor.fetchall.return_value = [
        (
            "SALES_USER",
            "SALES",
            "P_2026_Q1",
            1,
            "DATA_TS",
            100000,
            2500,
            "DISABLED",
            "TO_DATE('2026-04-01')",
            now,
        ),
    ]

    analyzer = OracleDiagnosticsAnalyzer(mock_driver, owner="SALES_USER", table_name="SALES")
    results = analyzer.analyze_partitions(mock_conn)

    assert len(results) == 1
    assert results[0].partition_name == "P_2026_Q1"
    assert results[0].partition_position == 1
    assert results[0].num_rows == 100000
    assert results[0].high_value == "TO_DATE('2026-04-01')"


def test_analyze_histograms() -> None:
    """Test column histogram metadata analysis."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
        ("SCOTT", "EMP", "DEPTNO", "FREQUENCY", 3, 3, 0, 14),
    ]

    analyzer = OracleDiagnosticsAnalyzer(mock_driver, owner="SCOTT", table_name="EMP")
    results = analyzer.analyze_histograms(mock_conn)

    assert len(results) == 1
    assert results[0].column_name == "DEPTNO"
    assert results[0].histogram_type == "FREQUENCY"
    assert results[0].num_buckets == 3


def test_analyze_lob_segments() -> None:
    """Test LOB segment storage and physical size metrics."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
        (
            "SCOTT",
            "DOCUMENTS",
            "CONTENT",
            "SYS_LOB001$",
            "LOB_TS",
            "NO",
            8192,
            "DEFAULT",
            "YES",
            10485760,
            5,
        ),
    ]

    analyzer = OracleDiagnosticsAnalyzer(mock_driver, owner="SCOTT", table_name="DOCUMENTS")
    results = analyzer.analyze_lob_segments(mock_conn)

    assert len(results) == 1
    assert results[0].column_name == "CONTENT"
    assert results[0].segment_name == "SYS_LOB001$"
    assert results[0].in_row == "NO"
    assert results[0].segment_bytes == 10485760


def test_analyze_redo_logs() -> None:
    """Test online redo log files and multiplexing metrics."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    mock_cursor.fetchall.side_effect = [
        # 1st query: v$log
        [(1, 1, 105, 52428800, 2, "CURRENT", "NO", now)],
        # 2nd query: v$logfile
        [
            (1, "/u01/app/oracle/oradata/redo01a.log"),
            (1, "/u02/app/oracle/oradata/redo01b.log"),
        ],
    ]

    analyzer = OracleDiagnosticsAnalyzer(mock_driver)
    results = analyzer.analyze_redo_logs(mock_conn)

    assert len(results) == 1
    assert results[0].group_number == 1
    assert results[0].status == "CURRENT"
    assert results[0].members == 2
    assert len(results[0].member_paths) == 2


def test_run_all_consolidation() -> None:
    """Test complete diagnostic report compilation with session execution."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session

    analyzer = OracleDiagnosticsAnalyzer(mock_driver)
    with (
        patch.object(analyzer, "analyze_sequential_reads", return_value=[]),
        patch.object(analyzer, "analyze_log_file_syncs", return_value=[]),
        patch.object(analyzer, "analyze_buffer_queue_stats", return_value=[]),
        patch.object(analyzer, "analyze_background_processes", return_value=[]),
        patch.object(analyzer, "analyze_user_quotas", return_value=[]),
        patch.object(analyzer, "analyze_buffer_pool_stats", return_value=[]),
        patch.object(analyzer, "analyze_index_stats", return_value=[]),
        patch.object(analyzer, "analyze_column_stats", return_value=[]),
        patch.object(analyzer, "analyze_table_storage", return_value=[]),
        patch.object(analyzer, "analyze_partitions", return_value=[]),
        patch.object(analyzer, "analyze_histograms", return_value=[]),
        patch.object(analyzer, "analyze_lob_segments", return_value=[]),
        patch.object(analyzer, "analyze_redo_logs", return_value=[]),
    ):
        report = analyzer.run_all()
        assert isinstance(report, DiagnosticsReport)


def test_format_report_text() -> None:
    """Test formatting full diagnostics report as plain text."""
    report = DiagnosticsReport(
        sequential_reads=[
            WaitEventMetric(
                event_name="db file sequential read",
                total_waits=100,
                total_timeouts=0,
                time_waited_ms=500.0,
                avg_wait_ms=5.0,
            )
        ],
        table_partitions=[
            TablePartitionInfo(
                owner="SCOTT",
                table_name="SALES",
                partition_name="P1",
                partition_position=1,
                tablespace_name="USERS",
                num_rows=500,
                blocks=20,
            )
        ],
        column_histograms=[
            HistogramInfo(
                owner="SCOTT",
                table_name="EMP",
                column_name="DEPTNO",
                histogram_type="FREQUENCY",
                num_buckets=3,
            )
        ],
        lob_segments=[
            LobSegmentInfo(
                owner="SCOTT",
                table_name="DOCS",
                column_name="BODY",
                segment_name="LOB_SEG_1",
                in_row="YES",
                segment_bytes=1048576,
            )
        ],
        redo_logs=[
            RedoLogInfo(
                group_number=1,
                thread_number=1,
                sequence_number=10,
                size_bytes=52428800,
                members=1,
                status="CURRENT",
                archived="NO",
                member_paths=["/oradata/redo01.log"],
            )
        ],
    )

    formatted = format_report_text(report)
    assert "ORACLE DATABASE DIAGNOSTIC & PERFORMANCE REPORT" in formatted
    assert "TABLE PARTITION ANALYSIS" in formatted
    assert "P1" in formatted
    assert "COLUMN HISTOGRAMS ANALYSIS" in formatted
    assert "FREQUENCY" in formatted
    assert "LOB SEGMENT STORAGE ANALYSIS" in formatted
    assert "LOB_SEG_1" in formatted
    assert "ONLINE REDO LOG GROUPS" in formatted
    assert "/oradata/redo01.log" in formatted


def test_main_cli_missing_credentials() -> None:
    """Test CLI returns exit code 1 when required arguments are missing."""
    with patch("sys.argv", ["oracle_diagnostics.py"]):
        assert main() == 1


def test_main_cli_success(tmp_path: Path) -> None:
    """Test CLI executes and saves report output."""
    output_file = tmp_path / "diagnostics.json"
    test_args = [
        "oracle_diagnostics.py",
        "--host",
        "db.local",
        "--service-name",
        "XE",
        "--user",
        "SYSTEM",
        "--password",
        "oracle",
        "--json",
        "--output",
        str(output_file),
    ]

    mock_report = DiagnosticsReport()

    with (
        patch("sys.argv", test_args),
        patch.object(OracleDiagnosticsAnalyzer, "run_all", return_value=mock_report),
    ):
        exit_code = main()
        assert exit_code == 0
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert '"table_partitions": []' in content
