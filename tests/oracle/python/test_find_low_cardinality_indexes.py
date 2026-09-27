"""Unit tests for Oracle low-cardinality index analyzer script."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import oracledb
import pytest
from pydantic import SecretStr, ValidationError

from oracle.python.find_low_cardinality_indexes import (
    LowCardinalityIndex,
    LowCardinalityIndexAnalyzer,
    LowCardinalityReport,
    OracleConnectionConfig,
    OracleDriver,
    build_parser,
    format_report_text,
    main,
)


def test_oracle_connection_config_valid() -> None:
    """Test valid configuration instantiation and field parsing."""
    config = OracleConnectionConfig(
        hostname="dbhost.example.com",
        port=1521,
        service_name="ORCLPDB1",
        username="c##dba",
        password=SecretStr("supersecret"),
        is_sysdba=True,
        owner="HR",
        table_name="EMPLOYEES",
        index_name="EMP_IDX",
        threshold_pct=2.5,
        min_rows=5000,
    )
    assert config.hostname == "dbhost.example.com"
    assert config.port == 1521
    assert config.service_name == "ORCLPDB1"
    assert config.username == "c##dba"
    assert config.password.get_secret_value() == "supersecret"
    assert "supersecret" not in repr(config.password)
    assert config.is_sysdba is True
    assert config.owner == "HR"
    assert config.table_name == "EMPLOYEES"
    assert config.index_name == "EMP_IDX"
    assert config.threshold_pct == 2.5
    assert config.min_rows == 5000


def test_oracle_connection_config_defaults() -> None:
    """Test default values for optional configuration parameters."""
    config = OracleConnectionConfig(
        username="test_user",
        password=SecretStr("password123"),
    )
    assert config.hostname == "localhost"
    assert config.port == 1521
    assert config.service_name is None
    assert config.sid is None
    assert config.is_sysdba is False
    assert config.owner is None
    assert config.table_name is None
    assert config.index_name is None
    assert config.threshold_pct == 5.0
    assert config.min_rows == 1000


def test_oracle_connection_config_extra_forbidden() -> None:
    """Test that extra configuration parameters are strictly rejected."""
    with pytest.raises(ValidationError):
        OracleConnectionConfig(
            username="user",
            password=SecretStr("pwd"),
            service_name="svc",
            extra_field="not_allowed",  # type: ignore[call-arg]
        )


def test_oracle_connection_config_missing_required() -> None:
    """Test failure on missing required fields."""
    with pytest.raises(ValidationError):
        OracleConnectionConfig(
            hostname="localhost",
            # missing username and password
        )  # type: ignore[call-arg]


def test_oracle_driver_session_service_name() -> None:
    """Test driver session opens connection using service name."""
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
        patch("oracledb.makedsn", return_value="MAKEDSN_STRING") as mock_makedsn,
        patch("oracledb.connect") as mock_connect,
    ):
        mock_connect.return_value.__enter__.return_value = mock_conn
        with driver.session() as conn:
            assert conn == mock_conn

        mock_makedsn.assert_called_once_with("db.test", 1521, service_name="MYSERVICE")
        mock_connect.assert_called_once_with(
            user="SCOTT",
            password="TIGER",
            dsn="MAKEDSN_STRING",
            mode=0,
        )


def test_oracle_driver_session_sid() -> None:
    """Test driver session opens connection using SID."""
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
        patch("oracledb.makedsn", return_value="MAKEDSN_SID") as mock_makedsn,
        patch("oracledb.connect") as mock_connect,
    ):
        mock_connect.return_value.__enter__.return_value = mock_conn
        with driver.session() as conn:
            assert conn == mock_conn

        mock_makedsn.assert_called_once_with("db.test", 1521, sid="ORCL")
        mock_connect.assert_called_once_with(
            user="SCOTT",
            password="TIGER",
            dsn="MAKEDSN_SID",
            mode=0,
        )


def test_oracle_driver_session_host_port_fallback() -> None:
    """Test driver session formats host:port when service name and SID are omitted."""
    config = OracleConnectionConfig(
        hostname="db.local",
        port=1526,
        username="APPUSER",
        password=SecretStr("PASS"),
    )
    driver = OracleDriver(config)

    mock_conn = MagicMock(spec=oracledb.Connection)
    with patch("oracledb.connect") as mock_connect:
        mock_connect.return_value.__enter__.return_value = mock_conn
        with driver.session() as conn:
            assert conn == mock_conn

        mock_connect.assert_called_once_with(
            user="APPUSER",
            password="PASS",
            dsn="db.local:1526",
            mode=0,
        )


def test_oracle_driver_session_sysdba_mode() -> None:
    """Test driver session connects with SYSDBA privilege when requested."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        service_name="ORCL",
        username="sys",
        password=SecretStr("syspassword"),
        is_sysdba=True,
    )
    driver = OracleDriver(config)

    mock_conn = MagicMock(spec=oracledb.Connection)
    with (
        patch("oracledb.makedsn", return_value="DSN"),
        patch("oracledb.connect") as mock_connect,
    ):
        mock_connect.return_value.__enter__.return_value = mock_conn
        with driver.session() as conn:
            assert conn == mock_conn

        mock_connect.assert_called_once_with(
            user="sys",
            password="syspassword",
            dsn="DSN",
            mode=oracledb.SYSDBA,
        )


def test_oracle_driver_session_failure() -> None:
    """Test driver raises DatabaseError on connection failure."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        service_name="ORCL",
        username="SCOTT",
        password=SecretStr("WRONG"),
    )
    driver = OracleDriver(config)

    with (
        patch("oracledb.connect", side_effect=oracledb.DatabaseError("ORA-01017")),
        pytest.raises(oracledb.DatabaseError),
        driver.session(),
    ):
        pass


def test_analyzer_happy_path() -> None:
    """Test analyzer correctly parses raw catalog rows and generates recommendations."""
    config = OracleConnectionConfig(
        username="user",
        password=SecretStr("pwd"),
        service_name="svc",
    )
    driver = OracleDriver(config)
    analyzer = LowCardinalityIndexAnalyzer(
        driver=driver,
        threshold_pct=5.0,
        min_rows=1000,
        owner_filter="APP",
        table_filter="ORDERS",
        index_filter="IDX_ORDERS_STATUS",
    )

    # Sample rows:
    # 0: owner, 1: index_name, 2: index_type, 3: table_owner, 4: table_name,
    # 5: uniqueness, 6: blevel, 7: leaf_blocks, 8: distinct_keys, 9: clustering_factor,
    # 10: num_rows, 11: column_name, 12: column_position, 13: descend
    sample_rows = [
        # Low cardinality index 1 (2 columns)
        (
            "APP",
            "IDX_ORDERS_STATUS",
            "NORMAL",
            "APP",
            "ORDERS",
            "NONUNIQUE",
            2,
            500,
            4,
            90000,
            100000,
            "STATUS",
            1,
            "ASC",
        ),
        (
            "APP",
            "IDX_ORDERS_STATUS",
            "NORMAL",
            "APP",
            "ORDERS",
            "NONUNIQUE",
            2,
            500,
            4,
            90000,
            100000,
            "ORDER_TYPE",
            2,
            "ASC",
        ),
        # High cardinality index (selectivity 50% > 5%) -> Not flagged
        (
            "APP",
            "IDX_ORDERS_CUSTOMER",
            "NORMAL",
            "APP",
            "ORDERS",
            "NONUNIQUE",
            1,
            200,
            50000,
            10000,
            100000,
            "CUSTOMER_ID",
            1,
            "ASC",
        ),
        # Small table (< min_rows 1000) -> Not evaluated
        (
            "APP",
            "IDX_LOOKUP_CODE",
            "NORMAL",
            "APP",
            "LOOKUP",
            "NONUNIQUE",
            1,
            10,
            2,
            50,
            500,
            "CODE",
            1,
            "ASC",
        ),
        # Low cardinality unique index with deep blevel
        (
            "APP",
            "IDX_FLAGS_PK",
            "NORMAL",
            "APP",
            "FLAGS",
            "UNIQUE",
            4,
            100,
            1,
            1500,
            2000,
            "FLAG_ID",
            1,
            "ASC",
        ),
    ]

    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = sample_rows

    with patch.object(driver, "session") as mock_session:
        mock_session.return_value.__enter__.return_value = mock_conn
        report = analyzer.analyze()

    assert report.threshold_pct == 5.0
    assert report.min_rows == 1000
    assert report.owner_filter == "APP"
    assert report.table_filter == "ORDERS"
    assert report.index_filter == "IDX_ORDERS_STATUS"
    assert report.total_indexes_evaluated == 3  # ORDERS STATUS, ORDERS CUSTOMER, FLAGS PK
    assert report.low_cardinality_count == 2  # ORDERS STATUS, FLAGS PK

    idx_status = next(i for i in report.items if i.index_name == "IDX_ORDERS_STATUS")
    assert idx_status.columns == ["STATUS", "ORDER_TYPE"]
    assert idx_status.distinct_keys == 4
    assert idx_status.num_rows == 100000
    assert idx_status.selectivity_ratio_pct == 0.0040
    assert idx_status.blevel == 2
    assert idx_status.leaf_blocks == 500
    assert idx_status.clustering_factor == 90000
    assert any("Bitmap index" in r for r in idx_status.recommendations)
    assert any("Extremely low selectivity" in r for r in idx_status.recommendations)
    assert any("High clustering factor" in r for r in idx_status.recommendations)

    idx_pk = next(i for i in report.items if i.index_name == "IDX_FLAGS_PK")
    assert idx_pk.columns == ["FLAG_ID"]
    assert idx_pk.distinct_keys == 1
    assert idx_pk.selectivity_ratio_pct == 0.05
    assert any("Distinct keys <= 1" in r for r in idx_pk.recommendations)
    assert any("High B-tree depth" in r for r in idx_pk.recommendations)
    assert any("unique constraint" in r for r in idx_pk.recommendations)


def test_analyzer_empty_results() -> None:
    """Test analyzer behavior when no indexes match criteria."""
    config = OracleConnectionConfig(
        username="user",
        password=SecretStr("pwd"),
        service_name="svc",
    )
    driver = OracleDriver(config)
    analyzer = LowCardinalityIndexAnalyzer(driver=driver)

    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    with patch.object(driver, "session") as mock_session:
        mock_session.return_value.__enter__.return_value = mock_conn
        report = analyzer.analyze()

    assert report.total_indexes_evaluated == 0
    assert report.low_cardinality_count == 0
    assert len(report.items) == 0


def test_analyzer_ora_00942_fallback() -> None:
    """Test analyzer falls back from DBA_ to ALL_ views on ORA-00942 error."""
    config = OracleConnectionConfig(
        username="appuser",
        password=SecretStr("pwd"),
        service_name="svc",
    )
    driver = OracleDriver(config)
    analyzer = LowCardinalityIndexAnalyzer(driver=driver)

    ora_00942 = oracledb.DatabaseError(MagicMock(code=942, message="ORA-00942: table or view does not exist"))

    all_views_rows = [
        (
            "APPUSER",
            "IDX_USER_STATUS",
            "NORMAL",
            "APPUSER",
            "APP_USERS",
            "NONUNIQUE",
            1,
            50,
            2,
            5000,
            10000,
            "STATUS",
            1,
            "ASC",
        )
    ]

    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # First execute fails with ORA-00942, second execute succeeds with fallback SQL
    mock_cursor.execute.side_effect = [ora_00942, None]
    mock_cursor.fetchall.return_value = all_views_rows

    with patch.object(driver, "session") as mock_session:
        mock_session.return_value.__enter__.return_value = mock_conn
        report = analyzer.analyze()

    assert mock_cursor.execute.call_count == 2
    assert report.total_indexes_evaluated == 1
    assert report.low_cardinality_count == 1
    assert report.items[0].index_name == "IDX_USER_STATUS"


def test_analyzer_fallback_query_failure() -> None:
    """Test analyzer re-raises DatabaseError if fallback query fails."""
    config = OracleConnectionConfig(
        username="user",
        password=SecretStr("pwd"),
        service_name="svc",
    )
    driver = OracleDriver(config)
    analyzer = LowCardinalityIndexAnalyzer(driver=driver)

    ora_00942 = oracledb.DatabaseError(MagicMock(code=942, message="ORA-00942: table or view does not exist"))
    ora_other = oracledb.DatabaseError(MagicMock(code=1000, message="ORA-01000: maximum open cursors exceeded"))

    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.execute.side_effect = [ora_00942, ora_other]

    with patch.object(driver, "session") as mock_session:
        mock_session.return_value.__enter__.return_value = mock_conn
        with pytest.raises(oracledb.DatabaseError):
            analyzer.analyze()


def test_analyzer_non_942_error_raises_immediately() -> None:
    """Test analyzer raises immediately without fallback on non-942 error."""
    config = OracleConnectionConfig(
        username="user",
        password=SecretStr("pwd"),
        service_name="svc",
    )
    driver = OracleDriver(config)
    analyzer = LowCardinalityIndexAnalyzer(driver=driver)

    ora_other = oracledb.DatabaseError(MagicMock(code=1031, message="ORA-01031: insufficient privileges"))

    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.execute.side_effect = ora_other

    with patch.object(driver, "session") as mock_session:
        mock_session.return_value.__enter__.return_value = mock_conn
        with pytest.raises(oracledb.DatabaseError):
            analyzer.analyze()

    assert mock_cursor.execute.call_count == 1


def test_format_report_text_with_items() -> None:
    """Test human-readable text formatting with low-cardinality findings."""
    item = LowCardinalityIndex(
        owner="SCOTT",
        index_name="IDX_EMP_JOB",
        table_owner="SCOTT",
        table_name="EMP",
        index_type="NORMAL",
        uniqueness="NONUNIQUE",
        columns=["JOB", "DEPTNO"],
        num_rows=50000,
        distinct_keys=5,
        selectivity_ratio_pct=0.0100,
        blevel=1,
        leaf_blocks=120,
        clustering_factor=45000,
        recommendations=["Bitmap candidate.", "High clustering factor."],
    )
    report = LowCardinalityReport(
        generated_at=datetime(2026, 9, 23, 14, 0, 0, tzinfo=timezone.utc),
        threshold_pct=5.0,
        min_rows=1000,
        owner_filter="SCOTT",
        table_filter="EMP",
        index_filter=None,
        total_indexes_evaluated=10,
        low_cardinality_count=1,
        items=[item],
    )
    text = format_report_text(report)
    assert "ORACLE LOW-CARDINALITY INDEX ANALYSIS REPORT" in text
    assert "SCOTT.IDX_EMP_JOB" in text
    assert "JOB, DEPTNO" in text
    assert "0.0100%" in text
    assert "Bitmap candidate." in text
    assert "High clustering factor." in text


def test_format_report_text_empty_items() -> None:
    """Test human-readable text formatting when no findings exist."""
    report = LowCardinalityReport(
        generated_at=datetime(2026, 9, 23, 14, 0, 0, tzinfo=timezone.utc),
        threshold_pct=5.0,
        min_rows=1000,
        owner_filter=None,
        table_filter=None,
        index_filter=None,
        total_indexes_evaluated=5,
        low_cardinality_count=0,
        items=[],
    )
    text = format_report_text(report)
    assert "No low-cardinality indexes found matching the criteria." in text


def test_main_clean_exit_code_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main returns 0 when no low-cardinality indexes are found."""
    mock_report = LowCardinalityReport(
        threshold_pct=5.0,
        min_rows=1000,
        total_indexes_evaluated=10,
        low_cardinality_count=0,
        items=[],
    )

    with patch(
        "oracle.python.find_low_cardinality_indexes.LowCardinalityIndexAnalyzer.analyze",
        return_value=mock_report,
    ):
        exit_code = main(
            [
                "--user",
                "testuser",
                "--password",
                "pwd",
                "--service-name",
                "svc",
            ]
        )
        assert exit_code == 0


def test_main_findings_exit_code_two() -> None:
    """Test main returns 2 when low-cardinality indexes are discovered."""
    item = LowCardinalityIndex(
        owner="APP",
        index_name="IDX_FLAG",
        table_owner="APP",
        table_name="FLAGS",
        index_type="NORMAL",
        uniqueness="NONUNIQUE",
        columns=["FLAG"],
        num_rows=2000,
        distinct_keys=2,
        selectivity_ratio_pct=0.1,
    )
    mock_report = LowCardinalityReport(
        threshold_pct=5.0,
        min_rows=1000,
        total_indexes_evaluated=5,
        low_cardinality_count=1,
        items=[item],
    )

    with patch(
        "oracle.python.find_low_cardinality_indexes.LowCardinalityIndexAnalyzer.analyze",
        return_value=mock_report,
    ):
        exit_code = main(
            [
                "--user",
                "testuser",
                "--password",
                "pwd",
                "--sid",
                "ORCL",
            ]
        )
        assert exit_code == 2


def test_main_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    """Test main outputs valid JSON structure with --json flag."""
    item = LowCardinalityIndex(
        owner="APP",
        index_name="IDX_STATUS",
        table_owner="APP",
        table_name="TBL",
        index_type="NORMAL",
        uniqueness="NONUNIQUE",
        columns=["STATUS"],
        num_rows=10000,
        distinct_keys=3,
        selectivity_ratio_pct=0.03,
    )
    mock_report = LowCardinalityReport(
        threshold_pct=5.0,
        min_rows=1000,
        total_indexes_evaluated=1,
        low_cardinality_count=1,
        items=[item],
    )

    with patch(
        "oracle.python.find_low_cardinality_indexes.LowCardinalityIndexAnalyzer.analyze",
        return_value=mock_report,
    ):
        exit_code = main(
            [
                "--user",
                "testuser",
                "--password",
                "pwd",
                "--service-name",
                "svc",
                "--json",
            ]
        )
        assert exit_code == 2

    captured = capsys.readouterr()
    assert '"low_cardinality_count": 1' in captured.out
    assert '"IDX_STATUS"' in captured.out


def test_main_output_file(tmp_path: Path) -> None:
    """Test main writes report content to specified file path."""
    out_file = tmp_path / "report.txt"
    mock_report = LowCardinalityReport(
        threshold_pct=5.0,
        min_rows=1000,
        total_indexes_evaluated=0,
        low_cardinality_count=0,
        items=[],
    )

    with patch(
        "oracle.python.find_low_cardinality_indexes.LowCardinalityIndexAnalyzer.analyze",
        return_value=mock_report,
    ):
        exit_code = main(
            [
                "--user",
                "testuser",
                "--password",
                "pwd",
                "--service-name",
                "svc",
                "--output",
                str(out_file),
            ]
        )
        assert exit_code == 0

    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "ORACLE LOW-CARDINALITY INDEX ANALYSIS REPORT" in content


def test_main_missing_user() -> None:
    """Test main returns 1 on missing user argument."""
    with patch.dict(os.environ, {}, clear=True):
        exit_code = main(["--password", "pwd", "--service-name", "svc"])
        assert exit_code == 1


def test_main_missing_password() -> None:
    """Test main returns 1 on missing password argument."""
    with patch.dict(os.environ, {}, clear=True):
        exit_code = main(["--user", "user", "--service-name", "svc"])
        assert exit_code == 1


def test_main_missing_service_name_and_sid() -> None:
    """Test main returns 1 on missing service name and sid."""
    with patch.dict(os.environ, {}, clear=True):
        exit_code = main(["--user", "user", "--password", "pwd"])
        assert exit_code == 1


def test_main_database_error() -> None:
    """Test main returns 1 when database operation raises DatabaseError."""
    with patch(
        "oracle.python.find_low_cardinality_indexes.LowCardinalityIndexAnalyzer.analyze",
        side_effect=oracledb.DatabaseError("DB connection failed"),
    ):
        exit_code = main(["--user", "user", "--password", "pwd", "--service-name", "svc"])
        assert exit_code == 1


def test_main_file_write_oserror(tmp_path: Path) -> None:
    """Test main returns 1 when output file cannot be written."""
    invalid_path = tmp_path / "non_existent_dir" / "nested" / "report.txt"
    mock_report = LowCardinalityReport(
        threshold_pct=5.0,
        min_rows=1000,
        total_indexes_evaluated=0,
        low_cardinality_count=0,
        items=[],
    )

    with patch(
        "oracle.python.find_low_cardinality_indexes.LowCardinalityIndexAnalyzer.analyze",
        return_value=mock_report,
    ):
        exit_code = main(
            [
                "--user",
                "testuser",
                "--password",
                "pwd",
                "--service-name",
                "svc",
                "--output",
                str(invalid_path),
            ]
        )
        assert exit_code == 1


def test_build_parser_env_vars() -> None:
    """Test parser picks up values from environment variables."""
    env_vars = {
        "ORACLE_HOST": "envhost",
        "ORACLE_PORT": "1525",
        "ORACLE_SERVICE_NAME": "ENV_SVC",
        "ORACLE_USER": "envuser",
        "ORACLE_PASSWORD": "envpassword",
        "ORACLE_OWNER": "ENV_OWNER",
        "ORACLE_TABLE": "ENV_TABLE",
        "ORACLE_INDEX": "ENV_INDEX",
        "ORACLE_THRESHOLD_PCT": "3.5",
        "ORACLE_MIN_ROWS": "2500",
    }
    with patch.dict(os.environ, env_vars, clear=True):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.host == "envhost"
        assert args.port == 1525
        assert args.service_name == "ENV_SVC"
        assert args.user == "envuser"
        assert args.password == "envpassword"
        assert args.owner == "ENV_OWNER"
        assert args.table == "ENV_TABLE"
        assert args.index == "ENV_INDEX"
        assert args.threshold_pct == 3.5
        assert args.min_rows == 2500
