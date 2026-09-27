"""Unit tests for Oracle invalid objects reporting script."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import oracledb
import pytest
from pydantic import SecretStr, ValidationError

from oracle.python.report_invalid_objects import (
    InvalidObject,
    InvalidObjectsReporter,
    ObjectCompileError,
    OracleConnectionConfig,
    OracleDriver,
    ReportSummary,
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
    )
    assert config.hostname == "dbhost.example.com"
    assert config.port == 1521
    assert config.service_name == "ORCLPDB1"
    assert config.username == "c##dba"
    assert config.password.get_secret_value() == "supersecret"
    assert "supersecret" not in repr(config.password)
    assert config.is_sysdba is True
    assert config.owner == "HR"


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


def test_oracle_driver_session_sysdba_mode() -> None:
    """Test driver session opens connection with SYSDBA mode when configured."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        sid="ORCL",
        username="SYS",
        password=SecretStr("change_on_install"),
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
            user="SYS",
            password="change_on_install",
            dsn="MAKEDSN_SID",
            mode=oracledb.SYSDBA,
        )


def test_oracle_driver_session_failure() -> None:
    """Test driver error handling when oracledb.connect fails."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        service_name="SVC",
        username="APP",
        password=SecretStr("SECRET"),
    )
    driver = OracleDriver(config)

    with (
        patch("oracledb.connect", side_effect=oracledb.DatabaseError("ORA-12541")),
        pytest.raises(oracledb.DatabaseError),
        driver.session(),
    ):
        pass


def test_reporter_generate_report_happy_path() -> None:
    """Test full report generation with invalid objects and matched compile errors."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    # 1st query: dba_objects, 2nd query: dba_errors
    mock_cursor.fetchall.side_effect = [
        [
            ("HR", "EMP_PKG", "PACKAGE BODY", "INVALID", now, now),
            ("HR", "EMP_VIEW", "VIEW", "INVALID", now, now),
        ],
        [
            (
                "HR",
                "EMP_PKG",
                "PACKAGE BODY",
                15,
                8,
                "PLS-00201: identifier 'DEPT' must be declared",
            ),
        ],
    ]

    reporter = InvalidObjectsReporter(mock_driver, owner_filter="HR")
    report = reporter.generate_report()

    assert report.total_invalid_objects == 2
    assert report.objects_by_type == {"PACKAGE BODY": 1, "VIEW": 1}
    assert report.objects_by_owner == {"HR": 2}
    assert len(report.items) == 2

    pkg_obj = report.items[0]
    assert pkg_obj.owner == "HR"
    assert pkg_obj.object_name == "EMP_PKG"
    assert len(pkg_obj.errors) == 1
    assert pkg_obj.errors[0].line == 15
    assert pkg_obj.errors[0].position == 8
    assert "PLS-00201" in pkg_obj.errors[0].text

    view_obj = report.items[1]
    assert view_obj.object_name == "EMP_VIEW"
    assert len(view_obj.errors) == 0


def test_reporter_generate_report_fallback_on_ora_942() -> None:
    """Test fallback from DBA_ views to ALL_ views when user lacks DBA privileges."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Simulate ORA-00942 on DBA_ query, success on ALL_ query
    ora_942_error = oracledb.DatabaseError()
    ora_error_obj = MagicMock()
    ora_error_obj.code = 942
    ora_942_error.args = (ora_error_obj,)

    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)

    # Sequence of cursor.execute results
    mock_cursor.execute.side_effect = [
        ora_942_error,  # DBA_OBJECTS fails
        None,  # ALL_OBJECTS succeeds
        ora_942_error,  # DBA_ERRORS fails
        None,  # ALL_ERRORS succeeds
    ]
    mock_cursor.fetchall.side_effect = [
        [("APP", "REPORT_PROC", "PROCEDURE", "INVALID", now, now)],
        [],
    ]

    reporter = InvalidObjectsReporter(mock_driver)
    report = reporter.generate_report()

    assert report.total_invalid_objects == 1
    assert report.items[0].object_name == "REPORT_PROC"


def test_format_report_text() -> None:
    """Test formatting report as human-readable text."""
    report = ReportSummary(
        total_invalid_objects=1,
        objects_by_type={"PACKAGE BODY": 1},
        objects_by_owner={"SCOTT": 1},
        items=[
            InvalidObject(
                owner="SCOTT",
                object_name="MY_PKG",
                object_type="PACKAGE BODY",
                status="INVALID",
                errors=[
                    ObjectCompileError(
                        line=42,
                        position=10,
                        text="PLS-00103: Encountered the symbol ';'",
                    )
                ],
            )
        ],
    )

    formatted = format_report_text(report)
    assert "ORACLE INVALID OBJECTS REPORT" in formatted
    assert "Total Invalid Objects: 1" in formatted
    assert "PACKAGE BODY" in formatted
    assert "SCOTT" in formatted
    assert "MY_PKG" in formatted
    assert "Line 42, Col 10: PLS-00103" in formatted


def test_format_report_text_empty() -> None:
    """Test formatting report text when no invalid objects exist."""
    report = ReportSummary(
        total_invalid_objects=0,
        objects_by_type={},
        objects_by_owner={},
        items=[],
    )
    formatted = format_report_text(report)
    assert "No invalid objects found in the database." in formatted


def test_main_cli_missing_credentials() -> None:
    """Test CLI returns exit code 1 when required arguments are missing."""
    with patch("sys.argv", ["report_invalid_objects.py"]):
        assert main() == 1


def test_main_cli_success(tmp_path: Path) -> None:
    """Test CLI runs successfully and writes report output."""
    output_file = tmp_path / "report.json"
    test_args = [
        "report_invalid_objects.py",
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

    mock_report = ReportSummary(
        total_invalid_objects=0,
        objects_by_type={},
        objects_by_owner={},
        items=[],
    )

    with (
        patch("sys.argv", test_args),
        patch.object(InvalidObjectsReporter, "generate_report", return_value=mock_report),
    ):
        exit_code = main()
        assert exit_code == 0
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert '"total_invalid_objects": 0' in content
