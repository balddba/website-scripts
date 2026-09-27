"""Unit tests for Oracle tablespace DDL generator script."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import oracledb
import pytest
from pydantic import SecretStr, ValidationError

from oracle.python.generate_tablespace_ddl import (
    DataFileInfo,
    OracleConnectionConfig,
    OracleDriver,
    TablespaceDdlGenerator,
    TablespaceDdlReport,
    TablespaceDdlResult,
    TablespaceMetadata,
    format_ddl_output,
    main,
)


def test_oracle_connection_config_valid() -> None:
    """Test valid configuration instantiation."""
    config = OracleConnectionConfig(
        hostname="db.example.com",
        port=1521,
        service_name="ORCLPDB1",
        username="c##admin",
        password=SecretStr("supersecret"),
        is_sysdba=True,
    )
    assert config.hostname == "db.example.com"
    assert config.port == 1521
    assert config.service_name == "ORCLPDB1"
    assert config.username == "c##admin"
    assert config.password.get_secret_value() == "supersecret"
    assert config.is_sysdba is True


def test_oracle_connection_config_extra_forbidden() -> None:
    """Test that extra fields raise validation errors."""
    with pytest.raises(ValidationError):
        OracleConnectionConfig(
            username="user",
            password=SecretStr("pass"),
            unknown_attr="fail",  # type: ignore[call-arg]
        )


def test_oracle_connection_config_missing_required() -> None:
    """Test that missing required fields raise validation errors."""
    with pytest.raises(ValidationError):
        OracleConnectionConfig(username="user")  # type: ignore[call-arg]


def test_oracle_driver_session_connect() -> None:
    """Test driver session connection establishment and close."""
    config = OracleConnectionConfig(
        hostname="localhost",
        port=1521,
        service_name="XEPDB1",
        username="testuser",
        password=SecretStr("testpass"),
        is_sysdba=True,
    )
    driver = OracleDriver(config)
    mock_conn = MagicMock(spec=oracledb.Connection)

    with patch("oracledb.connect", return_value=mock_conn) as mock_connect:
        with driver.session() as conn:
            assert conn is mock_conn
        mock_connect.assert_called_once_with(
            user="testuser",
            password="testpass",
            host="localhost",
            port=1521,
            service_name="XEPDB1",
            mode=oracledb.AUTH_MODE_SYSDBA,
        )
        mock_conn.close.assert_called_once()


def test_oracle_driver_session_failure() -> None:
    """Test driver session handling connection error."""
    config = OracleConnectionConfig(
        hostname="localhost",
        port=1521,
        service_name="XEPDB1",
        username="testuser",
        password=SecretStr("wrongpass"),
    )
    driver = OracleDriver(config)
    with (
        patch("oracledb.connect", side_effect=oracledb.DatabaseError("ORA-01017")),
        pytest.raises(oracledb.DatabaseError),
        driver.session(),
    ):
        pass


def test_get_tablespaces_happy_path() -> None:
    """Test querying tablespaces and datafiles."""
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Query 1: dba_tablespaces
    # tablespace_name, block_size, initial_extent, next_extent, min_extents, max_extents, pct_increase, status, contents, logging, extent_management, allocation_type, segment_space_management, bigfile, encrypted
    ts_rows = [
        (
            "USERS",
            8192,
            65536,
            1048576,
            1,
            2147483645,
            0,
            "ONLINE",
            "PERMANENT",
            "LOGGING",
            "LOCAL",
            "SYSTEM",
            "AUTO",
            "NO",
            "NO",
        ),
        (
            "TEMP",
            8192,
            1048576,
            1048576,
            1,
            None,
            0,
            "ONLINE",
            "TEMPORARY",
            "NOLOGGING",
            "LOCAL",
            "UNIFORM",
            "MANUAL",
            "NO",
            "NO",
        ),
    ]

    # Query 2: dba_data_files
    # tablespace_name, file_name, file_id, bytes, maxbytes, autoextensible, increment_bytes, status
    df_rows = [
        (
            "USERS",
            "/u01/app/oracle/oradata/users01.dbf",
            4,
            104857600,
            34359721984,
            "YES",
            10485760,
            "AVAILABLE",
        ),
    ]

    # Query 3: dba_temp_files
    tf_rows = [
        (
            "TEMP",
            "/u01/app/oracle/oradata/temp01.dbf",
            1,
            209715200,
            34359721984,
            "YES",
            10485760,
            "AVAILABLE",
        ),
    ]

    mock_cursor.fetchall.side_effect = [ts_rows, df_rows, tf_rows]

    mock_driver = MagicMock(spec=OracleDriver)
    mock_driver.session.return_value.__enter__.return_value = mock_conn

    generator = TablespaceDdlGenerator(mock_driver)
    tablespaces = generator.get_tablespaces()

    assert len(tablespaces) == 2
    users_ts = next(t for t in tablespaces if t.tablespace_name == "USERS")
    assert users_ts.contents == "PERMANENT"
    assert len(users_ts.datafiles) == 1
    assert users_ts.datafiles[0].file_name == "/u01/app/oracle/oradata/users01.dbf"
    assert users_ts.datafiles[0].autoextensible is True

    temp_ts = next(t for t in tablespaces if t.tablespace_name == "TEMP")
    assert temp_ts.contents == "TEMPORARY"
    assert len(temp_ts.datafiles) == 1
    assert temp_ts.datafiles[0].is_tempfile is True


def test_get_tablespaces_fallback_on_ora_942() -> None:
    """Test fallback from DBA_TABLESPACES to USER_TABLESPACES on ORA-00942."""
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    ora_942 = oracledb.DatabaseError("ORA-00942: table or view does not exist")
    ora_942_obj = MagicMock()
    ora_942_obj.code = 942
    ora_942.args = (ora_942_obj,)

    user_ts_rows = [
        (
            "USERS",
            8192,
            65536,
            1048576,
            1,
            2147483645,
            0,
            "ONLINE",
            "PERMANENT",
            "LOGGING",
            "LOCAL",
            "SYSTEM",
            "AUTO",
            "NO",
            "NO",
        ),
    ]

    # First call fails on DBA_TABLESPACES, second call succeeds on USER_TABLESPACES, datafiles/tempfiles fail gracefully
    mock_cursor.execute.side_effect = [ora_942, None, ora_942, ora_942]
    mock_cursor.fetchall.side_effect = [user_ts_rows]

    mock_driver = MagicMock(spec=OracleDriver)
    mock_driver.session.return_value.__enter__.return_value = mock_conn

    generator = TablespaceDdlGenerator(mock_driver)
    tablespaces = generator.get_tablespaces()

    assert len(tablespaces) == 1
    assert tablespaces[0].tablespace_name == "USERS"


def test_generate_ddl_dbms_metadata_success() -> None:
    """Test DBMS_METADATA DDL generation."""
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_clob = MagicMock()
    mock_clob.getvalue.return_value = "CREATE TABLESPACE USERS DATAFILE '/u01/oradata/users01.dbf' SIZE 100M;"
    mock_cursor.var.return_value = mock_clob

    mock_driver = MagicMock(spec=OracleDriver)
    mock_driver.session.return_value.__enter__.return_value = mock_conn

    generator = TablespaceDdlGenerator(mock_driver)
    ddl = generator.generate_ddl_dbms_metadata("USERS")

    assert "CREATE TABLESPACE USERS" in ddl
    assert ddl.endswith(";")


def test_generate_ddl_synthetic_permanent() -> None:
    """Test synthetic DDL construction for permanent tablespace."""
    mock_driver = MagicMock(spec=OracleDriver)
    generator = TablespaceDdlGenerator(mock_driver)

    meta = TablespaceMetadata(
        tablespace_name="APP_DATA",
        block_size=8192,
        status="ONLINE",
        contents="PERMANENT",
        logging="LOGGING",
        extent_management="LOCAL",
        allocation_type="SYSTEM",
        segment_space_management="AUTO",
        bigfile=False,
        datafiles=[
            DataFileInfo(
                file_name="/u01/app/oracle/oradata/app_data01.dbf",
                file_id=5,
                file_bytes=104857600,
                size_mb=100.0,
                max_bytes=10737418240,
                max_size_mb=10240.0,
                autoextensible=True,
                increment_by_bytes=10485760,
                status="AVAILABLE",
            ),
            DataFileInfo(
                file_name="/u01/app/oracle/oradata/app_data02.dbf",
                file_id=6,
                file_bytes=52428800,
                size_mb=50.0,
                max_bytes=0,
                max_size_mb=None,
                autoextensible=False,
                increment_by_bytes=0,
                status="AVAILABLE",
            ),
        ],
    )

    ddl = generator.generate_ddl_synthetic(meta, include_drop=True)

    assert "DROP TABLESPACE APP_DATA INCLUDING CONTENTS AND DATAFILES;" in ddl
    assert "CREATE TABLESPACE APP_DATA" in ddl
    assert "DATAFILE" in ddl
    assert "'/u01/app/oracle/oradata/app_data01.dbf' SIZE 100M AUTOEXTEND ON NEXT 10M MAXSIZE 10240M" in ddl
    assert "'/u01/app/oracle/oradata/app_data02.dbf' SIZE 50M AUTOEXTEND OFF" in ddl
    assert "LOGGING" in ddl
    assert "EXTENT MANAGEMENT LOCAL AUTOALLOCATE" in ddl
    assert "SEGMENT SPACE MANAGEMENT AUTO;" in ddl


def test_generate_ddl_synthetic_temporary_and_bigfile() -> None:
    """Test synthetic DDL construction for temporary and bigfile tablespaces."""
    mock_driver = MagicMock(spec=OracleDriver)
    generator = TablespaceDdlGenerator(mock_driver)

    temp_meta = TablespaceMetadata(
        tablespace_name="TEMP2",
        block_size=8192,
        status="ONLINE",
        contents="TEMPORARY",
        logging="NOLOGGING",
        extent_management="LOCAL",
        allocation_type="UNIFORM",
        next_extent=10485760,
        segment_space_management="MANUAL",
        bigfile=True,
        datafiles=[
            DataFileInfo(
                file_name="/u01/app/oracle/oradata/temp2_01.dbf",
                file_id=2,
                file_bytes=524288000,
                size_mb=500.0,
                max_bytes=0,
                max_size_mb=None,
                autoextensible=True,
                increment_by_bytes=52428800,
                status="AVAILABLE",
                is_tempfile=True,
            )
        ],
    )

    ddl = generator.generate_ddl_synthetic(temp_meta, include_drop=False)

    assert "CREATE BIGFILE TEMPORARY TABLESPACE TEMP2" in ddl
    assert "TEMPFILE '/u01/app/oracle/oradata/temp2_01.dbf' SIZE 500M AUTOEXTEND ON NEXT 50M MAXSIZE UNLIMITED" in ddl
    assert "EXTENT MANAGEMENT LOCAL UNIFORM SIZE 10M;" in ddl


def test_generate_ddl_synthetic_undo_and_readonly() -> None:
    """Test synthetic DDL construction for undo tablespaces and read-only status."""
    mock_driver = MagicMock(spec=OracleDriver)
    generator = TablespaceDdlGenerator(mock_driver)

    undo_meta = TablespaceMetadata(
        tablespace_name="UNDOTBS1",
        block_size=8192,
        status="READ ONLY",
        contents="UNDO",
        logging="LOGGING",
        extent_management="LOCAL",
        allocation_type="SYSTEM",
        segment_space_management="MANUAL",
        bigfile=False,
        datafiles=[],
    )

    ddl = generator.generate_ddl_synthetic(undo_meta, include_drop=False)

    assert "CREATE UNDO TABLESPACE UNDOTBS1" in ddl
    assert "ALTER TABLESPACE UNDOTBS1 READ ONLY;" in ddl


def test_generate_all_consolidation() -> None:
    """Test generate_all aggregating results with auto fallback."""
    meta = TablespaceMetadata(
        tablespace_name="DATA_TS",
        block_size=8192,
        status="ONLINE",
        contents="PERMANENT",
        logging="LOGGING",
        extent_management="LOCAL",
        allocation_type="SYSTEM",
        segment_space_management="AUTO",
        bigfile=False,
        datafiles=[],
    )

    mock_driver = MagicMock(spec=OracleDriver)
    generator = TablespaceDdlGenerator(mock_driver)

    with (
        patch.object(generator, "get_tablespaces", return_value=[meta]),
        patch.object(
            generator,
            "generate_ddl_dbms_metadata",
            side_effect=oracledb.DatabaseError("ORA-31603"),
        ),
    ):
        report = generator.generate_all(method="auto", include_drop=True)

    assert report.total_tablespaces == 1
    item = report.tablespaces[0]
    assert item.tablespace_name == "DATA_TS"
    assert item.generation_method == "SYNTHETIC"
    assert "CREATE TABLESPACE DATA_TS" in item.ddl


def test_format_ddl_output() -> None:
    """Test formatting report into SQL script text."""
    report = TablespaceDdlReport(
        generated_at="2026-09-23T12:00:00Z",
        total_tablespaces=1,
        tablespaces=[
            TablespaceDdlResult(
                tablespace_name="USERS",
                tablespace_type="PERMANENT",
                status="ONLINE",
                generation_method="DBMS_METADATA",
                ddl="CREATE TABLESPACE USERS DATAFILE '/u01/users01.dbf' SIZE 100M;",
            )
        ],
    )
    text = format_ddl_output(report, include_comments=True)
    assert "-- Oracle Tablespace DDL Extraction Script" in text
    assert "-- Tablespace: USERS" in text
    assert "CREATE TABLESPACE USERS" in text

    text_no_comments = format_ddl_output(report, include_comments=False)
    assert "-- Oracle Tablespace" not in text_no_comments
    assert "CREATE TABLESPACE USERS DATAFILE '/u01/users01.dbf' SIZE 100M;" in text_no_comments


def test_format_ddl_output_empty() -> None:
    """Test formatting when no tablespaces are present."""
    report = TablespaceDdlReport(
        generated_at="2026-09-23T12:00:00Z",
        total_tablespaces=0,
        tablespaces=[],
    )
    text = format_ddl_output(report)
    assert "-- No tablespaces found" in text


def test_main_cli_missing_credentials() -> None:
    """Test CLI exit code on missing credentials."""
    ret = main(["--host", "localhost"])
    assert ret == 1


def test_main_cli_success(tmp_path: Path) -> None:
    """Test main CLI entrypoint happy path with output file."""
    out_file = tmp_path / "tablespaces.sql"
    meta = TablespaceMetadata(
        tablespace_name="USERS",
        block_size=8192,
        status="ONLINE",
        contents="PERMANENT",
        logging="LOGGING",
        extent_management="LOCAL",
        allocation_type="SYSTEM",
        segment_space_management="AUTO",
        bigfile=False,
        datafiles=[],
    )

    with (
        patch.object(TablespaceDdlGenerator, "get_tablespaces", return_value=[meta]),
        patch.object(
            TablespaceDdlGenerator,
            "generate_ddl_dbms_metadata",
            return_value="CREATE TABLESPACE USERS;",
        ),
    ):
        ret = main(
            [
                "--user",
                "system",
                "--password",
                "manager",
                "--host",
                "localhost",
                "--output-file",
                str(out_file),
            ]
        )

    assert ret == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "CREATE TABLESPACE USERS;" in content
