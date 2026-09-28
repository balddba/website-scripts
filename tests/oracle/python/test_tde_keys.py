"""Unit tests for Oracle TDE encryption keys reporting script."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import oracledb
import pytest
from pydantic import SecretStr, ValidationError

from oracle.python.tde_keys import (
    ActiveMasterKey,
    KeyHealthCheck,
    KeyLifecycleRecord,
    KeystoreWallet,
    OracleConnectionConfig,
    OracleDriver,
    TablespaceKeyRecord,
    TdeKeyReport,
    TdeKeyReporter,
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
    )
    assert config.hostname == "dbhost.example.com"
    assert config.port == 1521
    assert config.service_name == "ORCLPDB1"
    assert config.username == "c##dba"
    assert config.password.get_secret_value() == "supersecret"
    assert config.is_sysdba is True


def test_oracle_connection_config_extra_forbidden() -> None:
    """Test that extra configuration parameters are strictly rejected."""
    with pytest.raises(ValidationError):
        OracleConnectionConfig(
            username="user",
            password=SecretStr("pwd"),
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
    with patch("oracledb.connect") as mock_connect:
        mock_connect.return_value.__enter__.return_value = mock_conn
        with driver.session() as conn:
            assert conn == mock_conn

        assert mock_connect.call_args[1]["mode"] == oracledb.SYSDBA


def test_tde_key_reporter_generate_report() -> None:
    """Test report generation aggregation across all key queries with PDB context."""
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    wallet_rows = [(1, 1, "CDB$ROOT", "FILE", "/opt/oracle/wallet/tde", "OPEN", "AUTOLOGIN", "PRIMARY", "YES")]
    active_key_rows = [
        ("CDB$ROOT", 1, "KEY_CDB_ROOT", "TDE IN-DATABASE MASTER KEY", "FILE", "2026-01-01 10:00:00", 30.5, "YES", "CDB_TAG"),
        ("ORCLPDB1", 3, "KEY_PDB1", "TDE IN-DATABASE MASTER KEY", "FILE", "2026-01-02 10:00:00", 29.5, "YES", "PDB1_TAG"),
    ]
    history_rows = [
        (
            "CDB$ROOT",
            1,
            "KEY_CDB_ROOT",
            "KEY_CDB_ROOT",
            "ACTIVE (CURRENT)",
            "TDE IN-DATABASE MASTER KEY",
            "FILE",
            "2026-01-01 09:00:00",
            "2026-01-01 10:00:00",
            "YES",
            "CDB_TAG",
        ),
        (
            "ORCLPDB1",
            3,
            "KEY_PDB1",
            "KEY_PDB1",
            "ACTIVE (CURRENT)",
            "TDE IN-DATABASE MASTER KEY",
            "FILE",
            "2026-01-02 09:00:00",
            "2026-01-02 10:00:00",
            "YES",
            "PDB1_TAG",
        ),
    ]
    ts_rows = [("ORCLPDB1", "SECURE_TS", "AES256", "NORMAL", "PRESENT")]
    health_rows = [
        ("Active Keystore Status", "OK", "All keystore instances and PDBs are OPEN."),
        ("Master Key Backed Up", "OK", "All master encryption keys are backed up in keystore."),
    ]

    mock_cursor.__iter__.side_effect = [
        iter(wallet_rows),
        iter(active_key_rows),
        iter(history_rows),
        iter(ts_rows),
        iter(health_rows),
    ]

    mock_driver = MagicMock(spec=OracleDriver)
    mock_driver.session.return_value.__enter__.return_value = mock_conn

    reporter = TdeKeyReporter(mock_driver)
    report = reporter.generate_report()

    assert len(report.wallets) == 1
    assert report.wallets[0].status == "OPEN"
    assert report.wallets[0].container_name == "CDB$ROOT"
    assert len(report.active_keys) == 2
    assert report.active_keys[0].pdb_name == "CDB$ROOT"
    assert report.active_keys[1].pdb_name == "ORCLPDB1"
    assert len(report.key_history) == 2
    assert report.key_history[1].pdb_name == "ORCLPDB1"
    assert len(report.tablespace_keys) == 1
    assert report.tablespace_keys[0].pdb_name == "ORCLPDB1"
    assert len(report.health_checks) == 2


def test_format_report_text_and_json() -> None:
    """Test text and JSON serialization formatting."""
    report = TdeKeyReport(
        generated_at="2026-09-28 12:00:00 UTC",
        wallets=[
            KeystoreWallet(
                inst_id=1,
                con_id=1,
                container_name="CDB$ROOT",
                wrl_type="FILE",
                wrl_parameter="/wallet/tde",
                status="OPEN",
                wallet_type="AUTOLOGIN",
                wallet_order="PRIMARY",
                fully_backed_up="YES",
            )
        ],
        active_keys=[
            ActiveMasterKey(
                pdb_name="ORCLPDB1",
                con_id=3,
                key_id="A1B2C3D4E5F6",
                key_use="TDE IN-DATABASE MASTER KEY",
                keystore_type="FILE",
                activated_time="2026-01-01 12:00:00",
                age_days=10.0,
                backed_up="YES",
                tag="ACTIVE_TAG",
            )
        ],
        key_history=[
            KeyLifecycleRecord(
                pdb_name="ORCLPDB1",
                con_id=3,
                key_id="A1B2C3D4E5F6",
                key_id_prefix="A1B2C3D4E5F6",
                key_status="ACTIVE (CURRENT)",
                key_use="TDE IN-DATABASE MASTER KEY",
                keystore_type="FILE",
                created_time="2026-01-01 10:00:00",
                activated_time="2026-01-01 12:00:00",
                backed_up="YES",
                tag="ACTIVE_TAG",
            )
        ],
        tablespace_keys=[
            TablespaceKeyRecord(
                pdb_name="ORCLPDB1",
                tablespace_name="DATA_TS",
                encryption_alg="AES256",
                key_status="NORMAL",
                encrypted_key_state="PRESENT",
            )
        ],
        health_checks=[
            KeyHealthCheck(
                check_name="Active Keystore Status",
                status="OK",
                details="All keystore instances are OPEN.",
            )
        ],
    )

    text = format_report_text(report)
    assert "Oracle Transparent Data Encryption (TDE) Key Information" in text
    assert "ORCLPDB1" in text
    assert "A1B2C3D4E5F6" in text
    assert "DATA_TS" in text
    assert "ACTIVE (CURRENT)" in text

    json_str = format_report_json(report)
    assert '"ORCLPDB1"' in json_str
    assert '"A1B2C3D4E5F6"' in json_str
    assert '"DATA_TS"' in json_str


def test_main_missing_credentials() -> None:
    """Test main returns 1 when credentials are missing."""
    assert main([]) == 1


def test_main_successful_execution(tmp_path) -> None:
    """Test main execution with valid arguments and file output."""
    out_file = tmp_path / "tde_keys.txt"

    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.__iter__.return_value = iter([])

    with patch("oracle.python.tde_keys.OracleDriver.session") as mock_session:
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
        assert "Oracle Transparent Data Encryption (TDE) Key Information" in content
