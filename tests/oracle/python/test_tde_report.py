"""Unit tests for Oracle TDE reporting script."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import oracledb
import pytest
from pydantic import SecretStr, ValidationError

from oracle.python.tde_report import (
    EncryptedColumn,
    EncryptedLob,
    EncryptedTableDetail,
    EncryptedTablespace,
    EncryptedTableSummary,
    KeystoreWallet,
    MasterEncryptionKey,
    OracleConnectionConfig,
    OracleDriver,
    TdeOverview,
    TdeParameter,
    TdeReport,
    TdeReporter,
    format_report_json,
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
        )  # type: ignore[call-arg]


def test_oracle_driver_session_service_name() -> None:
    """Test driver session opens connection using service name."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        service_name="MYSERVICE",
        username="SYSTEM",
        password=SecretStr("MANAGER"),
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
            user="SYSTEM",
            password="MANAGER",
            dsn="MAKEDSN_STRING",
            mode=0,
        )


def test_oracle_driver_session_sid() -> None:
    """Test driver session opens connection using SID."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        sid="ORCL",
        username="SYSTEM",
        password=SecretStr("MANAGER"),
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


def test_oracle_driver_session_sysdba_mode() -> None:
    """Test driver session opens connection with SYSDBA mode when configured."""
    config = OracleConnectionConfig(
        hostname="db.test",
        port=1521,
        service_name="SVC",
        username="SYS",
        password=SecretStr("PASSWORD"),
        is_sysdba=True,
    )
    driver = OracleDriver(config)

    mock_conn = MagicMock(spec=oracledb.Connection)
    with (
        patch("oracledb.connect") as mock_connect,
    ):
        mock_connect.return_value.__enter__.return_value = mock_conn
        with driver.session() as conn:
            assert conn == mock_conn

        assert mock_connect.call_args[1]["mode"] == oracledb.SYSDBA


def test_tde_reporter_generate_report() -> None:
    """Test report generation aggregation across all TDE queries."""
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    param_rows = [("encrypt_new_tablespaces", "ALWAYS"), ("wallet_root", "/opt/oracle/wallet")]
    wallet_rows = [(1, 1, "CDB$ROOT", "FILE", "/opt/oracle/wallet/tde", "OPEN", "AUTOLOGIN", "PRIMARY", "YES")]
    key_rows = [("CDB$ROOT", 1, "A1B2C3D4E5F6", "TDE IN-DATABASE MASTER KEY", "FILE", "2026-01-01 00:00:00", "2026-01-01 00:00:00", "PROD_KEY")]
    ts_rows = [
        ("ENCRYPTED_TBS", "PERMANENT", "ONLINE", "YES", "AES256", "NORMAL", 10.5),
        ("USERS", "PERMANENT", "ONLINE", "NO", "NONE", "UNENCRYPTED", 2.0),
    ]
    summary_rows = [("HR", "ENCRYPTED_TBS", 5, 5)]
    detail_rows = [("HR", "EMPLOYEES", "ENCRYPTED_TBS", "NO", 107, "AES256")]
    col_rows = [("HR", "EMPLOYEES", "SALARY", "AES 256 bits key", "YES", "SHA-1")]
    lob_rows = [("HR", "RESUMES", "DOC", "ENCRYPTED_TBS", "YES", "YES")]

    mock_cursor.__iter__.side_effect = [
        iter(param_rows),
        iter(wallet_rows),
        iter(key_rows),
        iter(ts_rows),
        iter(summary_rows),
        iter(detail_rows),
        iter(col_rows),
        iter(lob_rows),
    ]

    mock_driver = MagicMock(spec=OracleDriver)
    mock_driver.session.return_value.__enter__.return_value = mock_conn

    reporter = TdeReporter(mock_driver, owner_filter="HR")
    report = reporter.generate_report()

    assert report.overview.open_wallets == 1
    assert report.overview.encrypted_tablespaces == 1
    assert report.overview.total_tablespaces == 2
    assert report.overview.tables_in_encrypted_ts == 1
    assert report.overview.encrypted_columns == 1
    assert report.overview.encrypted_lobs == 1
    assert len(report.parameters) == 2
    assert len(report.wallets) == 1
    assert report.wallets[0].status == "OPEN"
    assert len(report.master_keys) == 1
    assert len(report.tablespaces) == 2
    assert len(report.table_summaries) == 1
    assert len(report.table_details) == 1
    assert len(report.columns) == 1
    assert len(report.lobs) == 1


def test_format_report_text_and_json() -> None:
    """Test text and JSON serialization formatting."""
    report = TdeReport(
        generated_at="2026-09-28 12:00:00 UTC",
        filter_owner="HR",
        overview=TdeOverview(
            open_wallets=1,
            encrypted_tablespaces=1,
            total_tablespaces=3,
            tables_in_encrypted_ts=2,
            encrypted_columns=1,
            encrypted_lobs=1,
        ),
        parameters=[TdeParameter(name="encrypt_new_tablespaces", value="ALWAYS")],
        wallets=[
            KeystoreWallet(
                inst_id=1,
                wrl_type="FILE",
                wrl_parameter="/wallet",
                status="OPEN",
                wallet_type="AUTOLOGIN",
                wallet_order="PRIMARY",
                fully_backed_up="YES",
            )
        ],
        master_keys=[
            MasterEncryptionKey(
                key_id="ABC123KEYID456",
                key_use="TDE MASTER KEY",
                keystore_type="FILE",
                creation_time="2026-01-01 10:00:00",
                activation_time="2026-01-01 10:00:00",
                tag="KEY1",
            )
        ],
        tablespaces=[
            EncryptedTablespace(
                tablespace_name="SECURE_TS",
                ts_type="PERMANENT",
                status="ONLINE",
                encrypted="YES",
                encryption_alg="AES256",
                tde_status="NORMAL",
                size_gb=15.0,
            )
        ],
        table_summaries=[
            EncryptedTableSummary(
                owner="HR",
                tablespace_name="SECURE_TS",
                table_count=2,
                segment_count=2,
            )
        ],
        table_details=[
            EncryptedTableDetail(
                owner="HR",
                table_name="PAYROLL",
                tablespace_name="SECURE_TS",
                partitioned="NO",
                num_rows=500,
                encryption_alg="AES256",
            )
        ],
        columns=[
            EncryptedColumn(
                owner="HR",
                table_name="PAYROLL",
                column_name="SALARY",
                encryption_alg="AES 256 bits key",
                salt="YES",
                integrity_alg="SHA-1",
            )
        ],
        lobs=[
            EncryptedLob(
                owner="HR",
                table_name="PAYROLL",
                column_name="CONTRACT",
                tablespace_name="SECURE_TS",
                securefile="YES",
                encrypt="YES",
            )
        ],
    )

    text = format_report_text(report)
    assert "Oracle Transparent Data Encryption (TDE) Report" in text
    assert "Open Wallets             : 1" in text
    assert "SECURE_TS" in text
    assert "PAYROLL" in text
    assert "SALARY" in text

    json_str = format_report_json(report)
    assert '"open_wallets": 1' in json_str
    assert '"SECURE_TS"' in json_str
    assert '"SALARY"' in json_str


def test_main_missing_credentials() -> None:
    """Test main returns 1 when credentials are missing."""
    assert main([]) == 1


def test_main_successful_execution(tmp_path) -> None:
    """Test main execution with valid arguments and file output."""
    out_file = tmp_path / "tde_report.txt"

    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.__iter__.return_value = iter([])

    with patch("oracle.python.tde_report.OracleDriver.session") as mock_session:
        mock_session.return_value.__enter__.return_value = mock_conn
        exit_code = main(
            [
                "--host",
                "localhost",
                "--service-name",
                "ORCL",
                "-u",
                "SYSTEM",
                "-p",
                "MANAGER",
                "-o",
                str(out_file),
            ]
        )
        assert exit_code == 0
        assert out_file.exists()
        content = out_file.read_text()
        assert "Oracle Transparent Data Encryption (TDE) Report" in content
