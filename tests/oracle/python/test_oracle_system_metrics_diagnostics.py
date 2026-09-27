"""Unit tests for Oracle system metrics and SQL parse diagnostics script."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import oracledb
import pytest
from pydantic import SecretStr, ValidationError

from oracle.python.oracle_system_metrics_diagnostics import (
    BufferPoolReport,
    BufferPoolStat,
    CacheAdviceEntry,
    CpuTimeModelMetric,
    CpuUsageReport,
    FileIoStat,
    HighParseSqlDetail,
    HighParseSqlReport,
    IoFunctionStat,
    IoStatReport,
    LatchMissDetail,
    LatchStatMetric,
    LatchStatsReport,
    OracleConnectionConfig,
    OracleDriver,
    OracleSystemMetricsAnalyzer,
    OsStatMetric,
    SystemMetricsDiagnosticsReport,
    SystemParseMetrics,
    TablespaceIoSummary,
    build_parser,
    format_system_metrics_report_text,
    main,
)


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
        username="SCOTT",
        password=SecretStr("TIGER"),
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
            user="SCOTT",
            password="TIGER",
            dsn="DSN_SID",
            mode=0,
        )


def test_oracle_driver_session_connect_host_port_only() -> None:
    """Test driver creates easy connect string without service or sid."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        username="SCOTT",
        password=SecretStr("TIGER"),
    )
    driver = OracleDriver(config)
    mock_conn = MagicMock(spec=oracledb.Connection)

    with patch("oracledb.connect", return_value=mock_conn) as mock_connect:
        with driver.session() as conn:
            assert conn == mock_conn

        mock_connect.assert_called_once_with(
            user="SCOTT",
            password="TIGER",
            dsn="db.test:1521",
            mode=0,
        )


def test_oracle_driver_session_sysdba_mode() -> None:
    """Test SYSDBA mode is used when user is SYS or is_sysdba is True."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        service_name="ORCL",
        username="sys",
        password=SecretStr("CHANGE_ON_INSTALL"),
        is_sysdba=False,
    )
    driver = OracleDriver(config)
    mock_conn = MagicMock(spec=oracledb.Connection)

    with (
        patch("oracledb.makedsn", return_value="DSN_SYS"),
        patch("oracledb.connect", return_value=mock_conn) as mock_connect,
    ):
        with driver.session():
            pass
        mock_connect.assert_called_once_with(
            user="sys",
            password="CHANGE_ON_INSTALL",
            dsn="DSN_SYS",
            mode=oracledb.SYSDBA,
        )


def test_oracle_driver_session_connect_error() -> None:
    """Test database connection error propagation."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        service_name="ORCL",
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
    """Test exception during connection closing is handled gracefully."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        service_name="ORCL",
        username="SCOTT",
        password=SecretStr("TIGER"),
    )
    driver = OracleDriver(config)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_conn.close.side_effect = oracledb.DatabaseError("Error closing")

    with (
        patch("oracledb.makedsn", return_value="DSN"),
        patch("oracledb.connect", return_value=mock_conn),
        driver.session() as conn,
    ):
        assert conn == mock_conn


# ---------------------------------------------------------------------------
# Analyzer 1: Buffer Pool Tests
# ---------------------------------------------------------------------------


def test_analyze_buffer_pool_success() -> None:
    """Test buffer pool analysis happy path with stats and cache advice."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_cursor = MagicMock()

    # Call 1: sysstat
    # Call 2: v$buffer_pool_statistics
    # Call 3: v$db_cache_advice
    mock_cursor.fetchall.side_effect = [
        [
            ("free buffer inspected", 1500),
            ("dirty buffers inspected", 250),
        ],
        [
            ("DEFAULT", 8192, 1024.0, 50000, 10000, 200000, 800000, 95.00),
            ("KEEP", 8192, 256.0, 100, 20, 5000, 15000, 99.50),
        ],
        [
            ("DEFAULT", 8192, 0.5, 512.0, 120000, 2.4, 250.0),
            ("DEFAULT", 8192, 1.0, 1024.0, 50000, 1.0, 100.0),
            ("DEFAULT", 8192, 1.5, 1536.0, 20000, 0.4, 40.0),
            ("RECYCLE", 8192, 1.0, 128.0, 5000, 1.0, 15.0),
        ],
    ]

    @contextmanager
    def fake_session():
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn

    mock_driver.session.side_effect = fake_session

    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver)
    report = analyzer.analyze_buffer_pool()

    assert isinstance(report, BufferPoolReport)
    assert report.free_buffer_inspected_total == 1500
    assert report.dirty_buffers_inspected_total == 250
    assert len(report.pools) == 3

    default_pool = next(p for p in report.pools if p.pool_name == "DEFAULT")
    assert default_pool.size_mb == 1024.0
    assert default_pool.physical_reads == 50000
    assert default_pool.cache_hit_ratio_pct == 95.0
    assert len(default_pool.cache_advice) == 3

    recycle_pool = next(p for p in report.pools if p.pool_name == "RECYCLE")
    assert recycle_pool.size_mb == 128.0
    assert len(recycle_pool.cache_advice) == 1


def test_analyze_buffer_pool_ora_00942() -> None:
    """Test buffer pool analysis handles ORA-00942 gracefully."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = oracledb.DatabaseError("ORA-00942: table or view does not exist")

    @contextmanager
    def fake_session():
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn

    mock_driver.session.side_effect = fake_session

    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver)
    report = analyzer.analyze_buffer_pool()
    assert isinstance(report, BufferPoolReport)
    assert len(report.pools) == 0


def test_analyze_buffer_pool_other_error() -> None:
    """Test buffer pool analysis raises non-ORA-00942 database errors."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = oracledb.DatabaseError("ORA-03113: end-of-file on communication channel")

    @contextmanager
    def fake_session():
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn

    mock_driver.session.side_effect = fake_session

    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver)
    with pytest.raises(oracledb.DatabaseError):
        analyzer.analyze_buffer_pool()


# ---------------------------------------------------------------------------
# Analyzer 2: CPU Usage Tests
# ---------------------------------------------------------------------------


def test_analyze_cpu_usage_success() -> None:
    """Test CPU usage analysis with time model and OS stats."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_cursor = MagicMock()

    # Call 1: v$sys_time_model
    # Call 2: v$osstat
    mock_cursor.fetchall.side_effect = [
        [
            ("DB time", 100.0),
            ("DB CPU", 60.0),
            ("background cpu time", 10.0),
            ("parse time cpu", 5.0),
            ("sql execute elapsed time", 55.0),
        ],
        [
            ("NUM_CPUS", 16.0, "Number of CPUs"),
            ("LOAD", 2.5, "Current OS load"),
            ("BUSY_TIME", 120000.0, "Busy CPU ticks"),
        ],
    ]

    @contextmanager
    def fake_session():
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn

    mock_driver.session.side_effect = fake_session

    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver)
    report = analyzer.analyze_cpu_usage()

    assert isinstance(report, CpuUsageReport)
    assert report.db_time_seconds == 100.0
    assert report.db_cpu_seconds == 60.0
    assert report.background_cpu_seconds == 10.0
    assert report.parse_time_cpu_seconds == 5.0
    assert report.sql_execute_cpu_seconds == 55.0
    assert report.cpu_time_pct_of_db_time == 60.0
    assert report.wait_time_pct_of_db_time == 40.0
    assert report.host_cpu_count == 16
    assert report.host_load == 2.5
    assert report.total_os_cpu_seconds == 1200.0
    assert len(report.time_model_metrics) == 5
    assert len(report.os_stats) == 3


def test_analyze_cpu_usage_user_sys_time() -> None:
    """Test OS CPU calculation using USER_TIME and SYS_TIME fallback."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_cursor = MagicMock()

    mock_cursor.fetchall.side_effect = [
        [],  # empty time model
        [
            ("NUM_CPU_CORES", 8.0, "Cores"),
            ("USER_TIME", 3000.0, "User ticks"),
            ("SYS_TIME", 2000.0, "Sys ticks"),
        ],
    ]

    @contextmanager
    def fake_session():
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn

    mock_driver.session.side_effect = fake_session

    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver)
    report = analyzer.analyze_cpu_usage()

    assert report.host_cpu_count == 8
    assert report.total_os_cpu_seconds == 50.0  # (3000 + 2000) / 100


def test_analyze_cpu_usage_ora_00942() -> None:
    """Test CPU usage handles missing views."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = oracledb.DatabaseError("ORA-00942: table or view does not exist")

    @contextmanager
    def fake_session():
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn

    mock_driver.session.side_effect = fake_session

    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver)
    report = analyzer.analyze_cpu_usage()
    assert report.db_time_seconds == 0.0
    assert report.host_cpu_count is None


# ---------------------------------------------------------------------------
# Analyzer 3: I/O Statistics Tests
# ---------------------------------------------------------------------------


def test_analyze_io_stats_primary_success() -> None:
    """Test I/O stats query using V$FILESTAT and V$IOSTAT_FUNCTION."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_cursor = MagicMock()

    mock_cursor.fetchall.side_effect = [
        [
            (
                "USERS",
                1,
                "/u01/app/oracle/oradata/users01.dbf",
                "DATA",
                10000,
                2000,
                50000.0,
                10000.0,
                5.0,
                5.0,
            ),
            (
                "USERS",
                2,
                "/u01/app/oracle/oradata/users02.dbf",
                "DATA",
                5000,
                1000,
                20000.0,
                4000.0,
                4.0,
                4.0,
            ),
            (
                "TEMP",
                1,
                "/u01/app/oracle/oradata/temp01.dbf",
                "TEMP",
                2000,
                3000,
                6000.0,
                9000.0,
                3.0,
                3.0,
            ),
        ],
        [
            ("DBWR", 0, 5000, 0.0, 20000.0),
            ("Direct Reads", 8000, 0, 24000.0, 0.0),
        ],
    ]

    @contextmanager
    def fake_session():
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn

    mock_driver.session.side_effect = fake_session

    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver)
    report = analyzer.analyze_io_stats()

    assert isinstance(report, IoStatReport)
    assert report.source_view == "V$FILESTAT"
    assert len(report.file_stats) == 3
    assert len(report.tablespace_summaries) == 2

    users_ts = next(ts for ts in report.tablespace_summaries if ts.tablespace_name == "USERS")
    assert users_ts.physical_reads == 15000
    assert users_ts.physical_writes == 3000
    assert users_ts.read_time_ms == 70000.0
    assert users_ts.avg_read_latency_ms == 4.67
    assert users_ts.avg_write_latency_ms == 4.67

    assert len(report.iostat_functions) == 2


def test_analyze_io_stats_fallback_to_iostat_file() -> None:
    """Test fallback to V$IOSTAT_FILE when V$FILESTAT raises ORA-00942."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_cursor = MagicMock()

    call_count = 0

    def mock_execute(sql, params=None):
        nonlocal call_count
        call_count += 1
        if "v$filestat" in sql.lower():
            raise oracledb.DatabaseError("ORA-00942: table or view does not exist")

    mock_cursor.execute.side_effect = mock_execute
    mock_cursor.fetchall.side_effect = [
        [
            (
                "UNKNOWN",
                1,
                "datafile_1.dbf",
                "DATA",
                8000,
                1000,
                16000.0,
                2000.0,
                2.0,
                2.0,
            ),
        ],
        [
            ("RMAN", 500, 500, 1000.0, 1000.0),
        ],
    ]

    @contextmanager
    def fake_session():
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn

    mock_driver.session.side_effect = fake_session

    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver)
    report = analyzer.analyze_io_stats()

    assert report.source_view == "V$IOSTAT_FILE"
    assert len(report.file_stats) == 1
    assert report.file_stats[0].file_name == "datafile_1.dbf"


def test_analyze_io_stats_fallback_ora_00942() -> None:
    """Test graceful handling when both primary and fallback views are unavailable."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = oracledb.DatabaseError("ORA-00942: table or view does not exist")

    @contextmanager
    def fake_session():
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn

    mock_driver.session.side_effect = fake_session

    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver)
    report = analyzer.analyze_io_stats()
    assert len(report.file_stats) == 0
    assert len(report.tablespace_summaries) == 0


# ---------------------------------------------------------------------------
# Analyzer 4: Latch Statistics Tests
# ---------------------------------------------------------------------------


def test_analyze_latch_stats_success() -> None:
    """Test latch statistics and miss breakdown."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_cursor = MagicMock()

    mock_cursor.fetchall.side_effect = [
        [
            ("cache buffers chains", 5000000, 1000, 2000, 500, 150, 450.5, 99.96, 7.5),
            ("shared pool", 1000000, 500, 1000, 200, 80, 200.0, 99.90, 8.0),
        ],
        [
            ("cache buffers chains", "kcbgtcr: fast path", 10, 120, 5),
            ("shared pool", "kghualloc", 5, 60, 2),
        ],
    ]

    @contextmanager
    def fake_session():
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn

    mock_driver.session.side_effect = fake_session

    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver)
    report = analyzer.analyze_latch_stats()

    assert isinstance(report, LatchStatsReport)
    assert len(report.latches) == 2
    assert report.latches[0].name == "cache buffers chains"
    assert report.latches[0].hit_ratio_pct == 99.96
    assert report.latches[0].sleep_rate_pct == 7.5
    assert len(report.latch_misses) == 2
    assert report.latch_misses[0].where_in_code == "kcbgtcr: fast path"


def test_analyze_latch_stats_ora_00942() -> None:
    """Test latch stats handles ORA-00942."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = oracledb.DatabaseError("ORA-00942: table or view does not exist")

    @contextmanager
    def fake_session():
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn

    mock_driver.session.side_effect = fake_session

    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver)
    report = analyzer.analyze_latch_stats()
    assert len(report.latches) == 0
    assert len(report.latch_misses) == 0


# ---------------------------------------------------------------------------
# Analyzer 5: High Parse SQL Tests
# ---------------------------------------------------------------------------


def test_analyze_high_parse_sql_success() -> None:
    """Test SQL parse analysis with offending SQL and root causes."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_cursor = MagicMock()

    mock_cursor.fetchall.side_effect = [
        [
            ("parse count (total)", 10000),
            ("parse count (hard)", 3000),
            ("parse count (failures)", 25),
            ("parse time cpu", 15000),
            ("session cursor cache hits", 2000),
        ],
        [
            (
                "3g8y729b8z71a",
                5000,
                500,
                10.0,
                2,
                0,
                250.0,
                500.0,
                "ORDER_SVC",
                "SELECT * FROM orders WHERE order_id = 123",
            ),
            (
                "4h8y729b8z71b",
                2000,
                2000,
                1.0,
                120,
                45,
                1000.0,
                2500.0,
                "INVENTORY",
                "SELECT * FROM items WHERE item_code = :bind1",
            ),
            (
                "5i8y729b8z71c",
                300,
                1,
                300.0,
                1,
                0,
                50.0,
                100.0,
                "BATCH",
                "INSERT INTO temp_tab VALUES (1, 'test')",
            ),
        ],
    ]

    @contextmanager
    def fake_session():
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn

    mock_driver.session.side_effect = fake_session

    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver, min_parses=100)
    report = analyzer.analyze_high_parse_sql()

    assert isinstance(report, HighParseSqlReport)
    assert report.system_parse_metrics is not None
    assert report.system_parse_metrics.parse_count_total == 10000
    assert report.system_parse_metrics.hard_parse_pct == 30.0
    assert report.system_parse_metrics.cursor_cache_hit_pct == 20.0
    assert report.system_parse_metrics.parse_time_cpu_seconds == 150.0

    assert len(report.overall_recommendations) == 3
    assert len(report.offending_sql) == 3

    # Statement 1: excessive parse per exec
    sql1 = report.offending_sql[0]
    assert sql1.sql_id == "3g8y729b8z71a"
    assert any("Excessive parse calls" in d for d in sql1.diagnoses)

    # Statement 2: high version count / invalidations
    sql2 = report.offending_sql[1]
    assert sql2.sql_id == "4h8y729b8z71b"
    assert any("High child cursor versions" in d for d in sql2.diagnoses)

    # Statement 3: unshared literal SQL
    sql3 = report.offending_sql[2]
    assert sql3.sql_id == "5i8y729b8z71c"
    assert any("Potential unshared literal SQL" in d for d in sql3.diagnoses)


def test_analyze_high_parse_sql_fallback_to_vsql() -> None:
    """Test fallback to V$SQL when V$SQLSTATS fails with ORA-00942."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_cursor = MagicMock()

    def mock_execute(sql, params=None):
        if "v$sqlstats" in sql.lower():
            raise oracledb.DatabaseError("ORA-00942: table or view does not exist")

    mock_cursor.execute.side_effect = mock_execute
    mock_cursor.fetchall.side_effect = [
        [],  # sysstat empty
        [
            ("sql123", 200, 100, 2.0, 1, 0, 10.0, 20.0, "APP", "SELECT 1 FROM DUAL"),
        ],
    ]

    @contextmanager
    def fake_session():
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn

    mock_driver.session.side_effect = fake_session

    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver)
    report = analyzer.analyze_high_parse_sql()

    assert len(report.offending_sql) == 1
    assert report.offending_sql[0].sql_id == "sql123"


def test_analyze_high_parse_sql_ora_00942_both() -> None:
    """Test graceful handling when both V$SQLSTATS and V$SQL fail."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = oracledb.DatabaseError("ORA-00942: table or view does not exist")

    @contextmanager
    def fake_session():
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_conn

    mock_driver.session.side_effect = fake_session

    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver)
    report = analyzer.analyze_high_parse_sql()
    assert report.system_parse_metrics is None
    assert len(report.offending_sql) == 0


# ---------------------------------------------------------------------------
# Consolidated run_all Tests
# ---------------------------------------------------------------------------


def test_run_all_consolidation() -> None:
    """Test run_all combines metrics from all 5 analyzers."""
    mock_driver = MagicMock(spec=OracleDriver)
    analyzer = OracleSystemMetricsAnalyzer(driver=mock_driver)

    with (
        patch.object(analyzer, "analyze_buffer_pool", return_value=BufferPoolReport()) as m_bp,
        patch.object(analyzer, "analyze_cpu_usage", return_value=CpuUsageReport()) as m_cpu,
        patch.object(analyzer, "analyze_io_stats", return_value=IoStatReport()) as m_io,
        patch.object(analyzer, "analyze_latch_stats", return_value=LatchStatsReport()) as m_latch,
        patch.object(analyzer, "analyze_high_parse_sql", return_value=HighParseSqlReport()) as m_sql,
    ):
        report = analyzer.run_all()
        assert isinstance(report, SystemMetricsDiagnosticsReport)
        assert report.buffer_pool is not None
        assert report.cpu_usage is not None
        assert report.io_stats is not None
        assert report.latch_stats is not None
        assert report.high_parse_sql is not None
        m_bp.assert_called_once()
        m_cpu.assert_called_once()
        m_io.assert_called_once()
        m_latch.assert_called_once()
        m_sql.assert_called_once()


# ---------------------------------------------------------------------------
# Text and JSON Formatting Tests
# ---------------------------------------------------------------------------


def test_format_system_metrics_report_text() -> None:
    """Test text report generation with complete dataset."""
    report = SystemMetricsDiagnosticsReport(
        timestamp=datetime(2026, 9, 23, 14, 0, 0, tzinfo=timezone.utc),
        buffer_pool=BufferPoolReport(
            pools=[
                BufferPoolStat(
                    pool_name="DEFAULT",
                    block_size_bytes=8192,
                    size_mb=1024.0,
                    physical_reads=5000,
                    physical_writes=1000,
                    db_block_gets=20000,
                    consistent_gets=80000,
                    cache_hit_ratio_pct=95.0,
                    free_buffer_inspected=100,
                    dirty_buffers_inspected=10,
                    cache_advice=[
                        CacheAdviceEntry(
                            pool_name="DEFAULT",
                            block_size_bytes=8192,
                            size_factor=1.0,
                            size_mb=1024.0,
                            estd_physical_reads=5000,
                            estd_physical_read_factor=1.0,
                            estd_physical_read_time_ms=50.0,
                        )
                    ],
                )
            ],
            free_buffer_inspected_total=100,
            dirty_buffers_inspected_total=10,
        ),
        cpu_usage=CpuUsageReport(
            db_cpu_seconds=50.0,
            background_cpu_seconds=10.0,
            parse_time_cpu_seconds=5.0,
            sql_execute_cpu_seconds=45.0,
            db_time_seconds=100.0,
            total_os_cpu_seconds=500.0,
            host_cpu_count=8,
            host_load=1.5,
            cpu_time_pct_of_db_time=50.0,
            wait_time_pct_of_db_time=50.0,
            time_model_metrics=[CpuTimeModelMetric(stat_name="DB CPU", time_seconds=50.0, pct_of_db_time=50.0)],
            os_stats=[OsStatMetric(stat_name="LOAD", value=1.5, comments="Load")],
        ),
        io_stats=IoStatReport(
            file_stats=[
                FileIoStat(
                    tablespace_name="USERS",
                    file_id=1,
                    file_name="/u01/users01.dbf",
                    file_type="DATA",
                    physical_reads=1000,
                    physical_writes=200,
                    read_time_ms=5000.0,
                    write_time_ms=1000.0,
                    avg_read_latency_ms=5.0,
                    avg_write_latency_ms=5.0,
                )
            ],
            tablespace_summaries=[
                TablespaceIoSummary(
                    tablespace_name="USERS",
                    physical_reads=1000,
                    physical_writes=200,
                    read_time_ms=5000.0,
                    write_time_ms=1000.0,
                    avg_read_latency_ms=5.0,
                    avg_write_latency_ms=5.0,
                )
            ],
            iostat_functions=[
                IoFunctionStat(
                    function_name="DBWR",
                    physical_reads=0,
                    physical_writes=200,
                    read_time_ms=0.0,
                    write_time_ms=1000.0,
                )
            ],
            source_view="V$FILESTAT",
        ),
        latch_stats=LatchStatsReport(
            latches=[
                LatchStatMetric(
                    name="cache buffers chains",
                    gets=100000,
                    immediate_gets=500,
                    misses=100,
                    spin_gets=50,
                    sleeps=10,
                    wait_time_ms=25.0,
                    hit_ratio_pct=99.9,
                    sleep_rate_pct=10.0,
                )
            ],
            latch_misses=[
                LatchMissDetail(
                    parent_name="cache buffers chains",
                    where_in_code="kcbgtcr: fast path",
                    nwfail_count=2,
                    sleep_count=10,
                    wtr_slp_count=1,
                )
            ],
        ),
        high_parse_sql=HighParseSqlReport(
            system_parse_metrics=SystemParseMetrics(
                parse_count_total=5000,
                parse_count_hard=1500,
                parse_count_failures=5,
                parse_time_cpu_seconds=25.0,
                session_cursor_cache_hits=1000,
                hard_parse_pct=30.0,
                cursor_cache_hit_pct=20.0,
            ),
            offending_sql=[
                HighParseSqlDetail(
                    sql_id="3g8y729b8z71a",
                    parse_calls=2500,
                    executions=250,
                    parse_per_exec_ratio=10.0,
                    version_count=1,
                    invalidations=0,
                    cpu_time_ms=500.0,
                    elapsed_time_ms=1200.0,
                    module="TEST_MOD",
                    sql_text="SELECT * FROM test WHERE id = 1",
                    diagnoses=["Excessive parse calls per execution."],
                )
            ],
            overall_recommendations=["High hard parse percentage (30.0%)."],
        ),
    )

    text = format_system_metrics_report_text(report)
    assert "ORACLE SYSTEM METRICS & SQL PARSE DIAGNOSTICS REPORT" in text
    assert "BUFFER POOL STATISTICS & CACHE ADVICE" in text
    assert "CPU USAGE & TIME MODEL STATISTICS" in text
    assert "I/O STATISTICS" in text
    assert "LATCH CONTENTION & MISS STATISTICS" in text
    assert "HIGH SQL PARSE RATES & OFFENDING SQL DIAGNOSIS" in text
    assert "3g8y729b8z71a" in text
    assert "cache buffers chains" in text
    assert "USERS" in text


def test_format_system_metrics_report_empty() -> None:
    """Test formatting when all reports are None or empty."""
    report = SystemMetricsDiagnosticsReport()
    text = format_system_metrics_report_text(report)
    assert "ORACLE SYSTEM METRICS & SQL PARSE DIAGNOSTICS REPORT" in text
    assert "BUFFER POOL STATISTICS: Not requested or unavailable" in text
    assert "CPU USAGE STATISTICS: Not requested or unavailable" in text
    assert "I/O STATISTICS: Not requested or unavailable" in text
    assert "LATCH STATISTICS: Not requested or unavailable" in text
    assert "HIGH SQL PARSE RATES: Not requested or unavailable" in text


def test_report_json_serialization() -> None:
    """Test report JSON dumping."""
    report = SystemMetricsDiagnosticsReport(
        timestamp=datetime(2026, 9, 23, 14, 0, 0, tzinfo=timezone.utc),
        buffer_pool=BufferPoolReport(),
    )
    json_str = report.model_dump_json(indent=2)
    assert '"timestamp":' in json_str
    assert '"buffer_pool":' in json_str


# ---------------------------------------------------------------------------
# CLI main() Tests
# ---------------------------------------------------------------------------


def test_build_parser() -> None:
    """Test CLI parser construction and argument defaults."""
    parser = build_parser()
    args = parser.parse_args(["-u", "scott", "-p", "tiger", "--service-name", "svc"])
    assert args.user == "scott"
    assert args.password == "tiger"
    assert args.service_name == "svc"
    assert args.analyzer == "all"
    assert args.top == 20
    assert args.min_parses == 100
    assert args.format == "text"
    assert args.output_file is None


def test_main_missing_user() -> None:
    """Test main exits with error when user is missing."""
    with patch.dict("os.environ", {}, clear=True):
        ret = main(["-p", "tiger", "--service-name", "svc"])
        assert ret == 1


def test_main_missing_password() -> None:
    """Test main exits with error when password is missing."""
    with patch.dict("os.environ", {}, clear=True):
        ret = main(["-u", "scott", "--service-name", "svc"])
        assert ret == 1


def test_main_missing_service_and_sid() -> None:
    """Test main exits with error when neither service nor sid provided."""
    with patch.dict("os.environ", {}, clear=True):
        ret = main(["-u", "scott", "-p", "tiger"])
        assert ret == 1


def test_main_success_all_analyzers(capsys: pytest.CaptureFixture[str]) -> None:
    """Test main executing with --analyzer all."""
    mock_report = SystemMetricsDiagnosticsReport(
        buffer_pool=BufferPoolReport(),
        cpu_usage=CpuUsageReport(),
        io_stats=IoStatReport(),
        latch_stats=LatchStatsReport(),
        high_parse_sql=HighParseSqlReport(),
    )

    with (
        patch("oracle.python.oracle_system_metrics_diagnostics.OracleDriver"),
        patch.object(
            OracleSystemMetricsAnalyzer,
            "run_all",
            return_value=mock_report,
        ),
    ):
        ret = main(["-u", "scott", "-p", "tiger", "--service-name", "svc", "--analyzer", "all"])
        assert ret == 0
        out, _ = capsys.readouterr()
        assert "ORACLE SYSTEM METRICS & SQL PARSE DIAGNOSTICS REPORT" in out


def test_main_individual_analyzers() -> None:
    """Test main invoking individual analyzer options."""
    analyzers = [
        ("buffer_pool", "analyze_buffer_pool", BufferPoolReport()),
        ("cpu_usage", "analyze_cpu_usage", CpuUsageReport()),
        ("io_stats", "analyze_io_stats", IoStatReport()),
        ("latch_stats", "analyze_latch_stats", LatchStatsReport()),
        ("high_parse_sql", "analyze_high_parse_sql", HighParseSqlReport()),
    ]

    for name, method_name, result_obj in analyzers:
        with (
            patch("oracle.python.oracle_system_metrics_diagnostics.OracleDriver"),
            patch.object(
                OracleSystemMetricsAnalyzer,
                method_name,
                return_value=result_obj,
            ) as mock_method,
        ):
            ret = main(
                [
                    "-u",
                    "scott",
                    "-p",
                    "tiger",
                    "--service-name",
                    "svc",
                    "--analyzer",
                    name,
                ]
            )
            assert ret == 0
            mock_method.assert_called_once()


def test_main_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    """Test main outputting JSON format."""
    mock_report = SystemMetricsDiagnosticsReport(buffer_pool=BufferPoolReport())

    with (
        patch("oracle.python.oracle_system_metrics_diagnostics.OracleDriver"),
        patch.object(
            OracleSystemMetricsAnalyzer,
            "run_all",
            return_value=mock_report,
        ),
    ):
        ret = main(
            [
                "-u",
                "scott",
                "-p",
                "tiger",
                "--service-name",
                "svc",
                "--format",
                "json",
            ]
        )
        assert ret == 0
        out, _ = capsys.readouterr()
        assert '"buffer_pool":' in out


def test_main_output_file(tmp_path: Path) -> None:
    """Test main writing output to a file."""
    output_file = tmp_path / "diagnostics.txt"
    mock_report = SystemMetricsDiagnosticsReport(buffer_pool=BufferPoolReport())

    with (
        patch("oracle.python.oracle_system_metrics_diagnostics.OracleDriver"),
        patch.object(
            OracleSystemMetricsAnalyzer,
            "run_all",
            return_value=mock_report,
        ),
    ):
        ret = main(
            [
                "-u",
                "scott",
                "-p",
                "tiger",
                "--service-name",
                "svc",
                "-o",
                str(output_file),
            ]
        )
        assert ret == 0
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "ORACLE SYSTEM METRICS & SQL PARSE DIAGNOSTICS REPORT" in content


def test_main_output_file_error(tmp_path: Path) -> None:
    """Test main handling output file write failure."""
    output_file = tmp_path / "non_existent_dir" / "nested" / "diagnostics.txt"
    mock_report = SystemMetricsDiagnosticsReport()

    with (
        patch("oracle.python.oracle_system_metrics_diagnostics.OracleDriver"),
        patch.object(
            OracleSystemMetricsAnalyzer,
            "run_all",
            return_value=mock_report,
        ),
    ):
        ret = main(
            [
                "-u",
                "scott",
                "-p",
                "tiger",
                "--service-name",
                "svc",
                "-o",
                str(output_file),
            ]
        )
        assert ret == 1


def test_main_database_error() -> None:
    """Test main handling top-level database error."""
    with (
        patch("oracle.python.oracle_system_metrics_diagnostics.OracleDriver"),
        patch.object(
            OracleSystemMetricsAnalyzer,
            "run_all",
            side_effect=oracledb.DatabaseError("ORA-01017: invalid username/password"),
        ),
    ):
        ret = main(["-u", "scott", "-p", "wrong_pwd", "--service-name", "svc"])
        assert ret == 1
