"""Unit tests for Oracle directory objects listing script."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import oracledb
import pytest
from pydantic import SecretStr, ValidationError

from oracle.python.list_directory_objects import (
    DirectoryObject,
    DirectoryObjectsLister,
    DirectoryPrivilege,
    DirectoryReportSummary,
    OracleConnectionConfig,
    OracleDriver,
    format_directories_text,
    main,
)


def test_oracle_connection_config_valid() -> None:
    """Test valid configuration instantiation and field parsing."""
    config = OracleConnectionConfig(
        hostname="dbhost.example.com",
        port=1521,
        service_name="ORCLPDB1",
        username="c##dba",
        password=SecretStr("secret_pwd"),
        is_sysdba=True,
        directory_filter="DATA_PUMP",
    )
    assert config.hostname == "dbhost.example.com"
    assert config.port == 1521
    assert config.service_name == "ORCLPDB1"
    assert config.username == "c##dba"
    assert config.password.get_secret_value() == "secret_pwd"
    assert "secret_pwd" not in repr(config.password)
    assert config.is_sysdba is True
    assert config.directory_filter == "DATA_PUMP"


def test_oracle_connection_config_extra_forbidden() -> None:
    """Test that extra configuration parameters are strictly rejected."""
    with pytest.raises(ValidationError):
        OracleConnectionConfig(
            username="user",
            password=SecretStr("pwd"),
            service_name="svc",
            extra_field="disallowed",  # type: ignore[call-arg]
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
        username="SYS",
        password=SecretStr("change_on_install"),
        is_sysdba=True,
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


def test_lister_list_directories_happy_path_with_privs() -> None:
    """Test directory listing and privilege resolution."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # 1st query: dba_directories, 2nd query: dba_tab_privs
    mock_cursor.fetchall.side_effect = [
        [
            ("SYS", "DATA_PUMP_DIR", "/opt/oracle/admin/dpdump"),
            ("SYS", "EXT_TABLE_DIR", "/data/ext_tables"),
        ],
        [
            ("DATA_PUMP_DIR", "EXP_FULL_DATABASE", "READ", "NO"),
            ("DATA_PUMP_DIR", "EXP_FULL_DATABASE", "WRITE", "NO"),
            ("EXT_TABLE_DIR", "APP_USER", "READ", "YES"),
        ],
    ]

    lister = DirectoryObjectsLister(mock_driver, directory_filter="DIR")
    report = lister.list_directories()

    assert report.total_directories == 2
    assert len(report.directories) == 2

    dp_dir = report.directories[0]
    assert dp_dir.directory_name == "DATA_PUMP_DIR"
    assert dp_dir.directory_path == "/opt/oracle/admin/dpdump"
    assert len(dp_dir.privileges) == 2
    assert dp_dir.privileges[0].grantee == "EXP_FULL_DATABASE"
    assert dp_dir.privileges[0].privilege == "READ"

    ext_dir = report.directories[1]
    assert ext_dir.directory_name == "EXT_TABLE_DIR"
    assert len(ext_dir.privileges) == 1
    assert ext_dir.privileges[0].grantable == "YES"


def test_lister_list_directories_fallback_on_ora_942() -> None:
    """Test fallback from DBA_DIRECTORIES to ALL_DIRECTORIES on ORA-00942."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    ora_942_error = oracledb.DatabaseError()
    ora_error_obj = MagicMock()
    ora_error_obj.code = 942
    ora_942_error.args = (ora_error_obj,)

    # Sequence of cursor.execute results
    mock_cursor.execute.side_effect = [
        ora_942_error,  # DBA_DIRECTORIES fails
        None,  # ALL_DIRECTORIES succeeds
        ora_942_error,  # DBA_TAB_PRIVS fails
        None,  # ALL_TAB_PRIVS succeeds
    ]
    mock_cursor.fetchall.side_effect = [
        [("SYS", "USER_DIR", "/home/oracle/dir")],
        [],
    ]

    lister = DirectoryObjectsLister(mock_driver)
    report = lister.list_directories()

    assert report.total_directories == 1
    assert report.directories[0].directory_name == "USER_DIR"


def test_lister_privileges_query_failure_graceful() -> None:
    """Test that failure in privileges query logs a warning and does not crash."""
    mock_driver = MagicMock(spec=OracleDriver)
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)

    @contextmanager
    def mock_session():
        yield mock_conn

    mock_driver.session = mock_session
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.side_effect = [
        [("SYS", "MY_DIR", "/tmp/dir")],
    ]
    mock_cursor.execute.side_effect = [
        None,  # directories query succeeds
        oracledb.DatabaseError("ORA-01031: insufficient privileges"),  # privs query fails
    ]

    lister = DirectoryObjectsLister(mock_driver)
    report = lister.list_directories()

    assert report.total_directories == 1
    assert report.directories[0].directory_name == "MY_DIR"
    assert report.directories[0].privileges == []


def test_format_directories_text() -> None:
    """Test formatting directory report as human-readable text."""
    report = DirectoryReportSummary(
        total_directories=1,
        directories=[
            DirectoryObject(
                owner="SYS",
                directory_name="EXPORT_DIR",
                directory_path="/u01/app/oracle/export",
                privileges=[
                    DirectoryPrivilege(
                        grantee="SCOTT",
                        privilege="READ",
                        grantable="YES",
                    )
                ],
            )
        ],
    )

    formatted = format_directories_text(report, show_privileges=True)
    assert "ORACLE DIRECTORY OBJECTS REPORT" in formatted
    assert "Total Directories: 1" in formatted
    assert "EXPORT_DIR" in formatted
    assert "/u01/app/oracle/export" in formatted
    assert "Grantee: SCOTT" in formatted
    assert "Privilege: READ (ADMIN)" in formatted


def test_format_directories_text_empty() -> None:
    """Test formatting directory report text when no directory objects exist."""
    report = DirectoryReportSummary(
        total_directories=0,
        directories=[],
    )
    formatted = format_directories_text(report)
    assert "No directory objects found in the database." in formatted


def test_main_cli_missing_credentials() -> None:
    """Test CLI returns exit code 1 when required arguments are missing."""
    with patch("sys.argv", ["list_directory_objects.py"]):
        assert main() == 1


def test_main_cli_success(tmp_path: Path) -> None:
    """Test CLI runs successfully and writes report output."""
    output_file = tmp_path / "directories.json"
    test_args = [
        "list_directory_objects.py",
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

    mock_report = DirectoryReportSummary(
        total_directories=0,
        directories=[],
    )

    with (
        patch("sys.argv", test_args),
        patch.object(DirectoryObjectsLister, "list_directories", return_value=mock_report),
    ):
        exit_code = main()
        assert exit_code == 0
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert '"total_directories": 0' in content
