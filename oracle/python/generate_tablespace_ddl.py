#!/usr/bin/env python3
#===============================================================================
#
# Script Name: generate_tablespace_ddl.py
# Title: Generate Oracle tablespace DDL
# Tags: Python, Tablespaces, DDL
# Purpose: Generate recreation DDL for Oracle permanent and temporary tablespaces.
#
# Description:
#   Reads tablespace and data-file metadata and produces SQL suitable for
#   reviewing or recreating the selected tablespaces.
#
# Parameters:
#   Command-line Oracle connection settings and tablespace filters; use --help.
#
# Required Privileges:
#   - Read access to the Oracle catalog views queried by the script
#
# Output Format:
#   - SQL DDL written to standard output or the requested output file
#
# Example Usage:
#   python generate_tablespace_ddl.py --help
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
"""Generate DDL scripts for Oracle tablespaces."""

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


class OracleConnectionConfig(BaseModel):
    """Configuration for connecting to an Oracle database.

    Attributes:
        hostname: Database host address or IP.
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


class DataFileInfo(BaseModel):
    """Details of a data file or temp file associated with a tablespace.

    Attributes:
        file_name: Physical path and name of the data file.
        file_id: Numeric identifier of the file.
        file_bytes: Size of file in bytes.
        size_mb: Size of file in megabytes.
        max_bytes: Maximum allowed size in bytes (0 if not specified).
        max_size_mb: Maximum allowed size in megabytes if autoextensible.
        autoextensible: Whether the file automatically extends.
        increment_by_bytes: Increment chunk size in bytes.
        status: File status (e.g. AVAILABLE, ONLINE).
        is_tempfile: Whether this is a temporary file.
    """

    model_config = {"extra": "forbid"}

    file_name: str
    file_id: int
    file_bytes: int
    size_mb: float
    max_bytes: int = 0
    max_size_mb: float | None = None
    autoextensible: bool = False
    increment_by_bytes: int = 0
    status: str = "AVAILABLE"
    is_tempfile: bool = False


class TablespaceMetadata(BaseModel):
    """Metadata describing an Oracle tablespace and its storage parameters.

    Attributes:
        tablespace_name: Name of the tablespace.
        block_size: Database block size in bytes.
        initial_extent: Size of initial extent in bytes.
        next_extent: Size of next extent in bytes.
        min_extents: Minimum number of extents.
        max_extents: Maximum number of extents.
        pct_increase: Percentage increase for extents.
        status: Status (ONLINE, OFFLINE, READ ONLY).
        contents: Type of contents (PERMANENT, TEMPORARY, UNDO).
        logging: Logging attribute (LOGGING, NOLOGGING).
        extent_management: Extent allocation model (LOCAL, DICTIONARY).
        allocation_type: Allocation algorithm (SYSTEM, UNIFORM, USER).
        segment_space_management: Free space tracking (AUTO, MANUAL).
        bigfile: True if bigfile tablespace.
        encrypted: True if encrypted.
        datafiles: List of data files or temp files.
    """

    model_config = {"extra": "forbid"}

    tablespace_name: str
    block_size: int
    initial_extent: int | None = None
    next_extent: int | None = None
    min_extents: int | None = None
    max_extents: int | None = None
    pct_increase: int | None = None
    status: str = "ONLINE"
    contents: str = "PERMANENT"
    logging: str = "LOGGING"
    extent_management: str = "LOCAL"
    allocation_type: str = "SYSTEM"
    segment_space_management: str = "AUTO"
    bigfile: bool = False
    encrypted: bool | None = None
    datafiles: list[DataFileInfo] = Field(default_factory=list)


class TablespaceDdlResult(BaseModel):
    """DDL generation output for a single tablespace.

    Attributes:
        tablespace_name: Name of the tablespace.
        tablespace_type: Type of tablespace (PERMANENT, TEMPORARY, UNDO).
        status: Current status of the tablespace.
        generation_method: Method used to generate DDL (DBMS_METADATA or SYNTHETIC).
        ddl: Full DDL statement.
        metadata: Detailed tablespace metadata if retrieved.
    """

    model_config = {"extra": "forbid"}

    tablespace_name: str
    tablespace_type: str
    status: str
    generation_method: str
    ddl: str
    metadata: TablespaceMetadata | None = None


class TablespaceDdlReport(BaseModel):
    """Consolidated report containing generated DDL for tablespaces.

    Attributes:
        generated_at: ISO 8601 timestamp of generation.
        total_tablespaces: Count of tablespaces included.
        tablespaces: List of individual tablespace DDL results.
    """

    model_config = {"extra": "forbid"}

    generated_at: str
    total_tablespaces: int
    tablespaces: list[TablespaceDdlResult]


class OracleDriver:
    """Manages database connections to Oracle using python-oracledb Thin mode."""

    def __init__(self, config: OracleConnectionConfig) -> None:
        """Initialize driver with connection configuration.

        Args:
            config: Validated database connection configuration.
        """
        self._config = config

    @contextmanager
    def session(self) -> Generator[oracledb.Connection, None, None]:
        """Context manager providing an active Oracle connection.

        Yields:
            oracledb.Connection: Active database connection.

        Raises:
            oracledb.DatabaseError: If connection cannot be established.
        """
        params: dict[str, Any] = {
            "user": self._config.username,
            "password": self._config.password.get_secret_value(),
            "host": self._config.hostname,
            "port": self._config.port,
        }
        if self._config.service_name:
            params["service_name"] = self._config.service_name
        elif self._config.sid:
            params["sid"] = self._config.sid
        else:
            params["service_name"] = "ORCLCDB"

        if self._config.is_sysdba:
            params["mode"] = oracledb.AUTH_MODE_SYSDBA

        logger.debug(
            "Connecting to Oracle host={} port={} sysdba={}",
            self._config.hostname,
            self._config.port,
            self._config.is_sysdba,
        )
        conn = oracledb.connect(**params)
        try:
            yield conn
        finally:
            conn.close()
            logger.debug("Oracle connection closed")


class TablespaceDdlGenerator:
    """Extracts tablespace metadata and generates DDL statements."""

    def __init__(self, driver: OracleDriver) -> None:
        """Initialize generator with an Oracle driver.

        Args:
            driver: Oracle database connection driver.
        """
        self._driver = driver

    def get_tablespaces(
        self,
        tablespace_filter: str | None = None,
        type_filter: str | None = None,
    ) -> list[TablespaceMetadata]:
        """Query tablespace definitions and datafiles from data dictionary views.

        Args:
            tablespace_filter: Optional specific tablespace name to filter by.
            type_filter: Optional type filter (e.g. PERMANENT, TEMPORARY, UNDO).

        Returns:
            list[TablespaceMetadata]: List of tablespaces with associated datafiles.
        """
        with self._driver.session() as conn, conn.cursor() as cursor:
            ts_dict = self._fetch_tablespace_headers(cursor, tablespace_filter, type_filter)
            self._populate_datafiles(cursor, ts_dict)
            self._populate_tempfiles(cursor, ts_dict)
            return list(ts_dict.values())

    def _fetch_tablespace_headers(
        self,
        cursor: oracledb.Cursor,
        tablespace_filter: str | None,
        type_filter: str | None,
    ) -> dict[str, TablespaceMetadata]:
        """Fetch base tablespace headers from DBA_TABLESPACES or USER_TABLESPACES.

        Args:
            cursor: Active database cursor.
            tablespace_filter: Optional tablespace name filter.
            type_filter: Optional tablespace type filter.

        Returns:
            dict[str, TablespaceMetadata]: Map of tablespace name to metadata object.
        """
        clauses: list[str] = ["1=1"]
        binds: dict[str, Any] = {}

        if tablespace_filter:
            clauses.append("UPPER(tablespace_name) = UPPER(:ts_name)")
            binds["ts_name"] = tablespace_filter

        if type_filter and type_filter.upper() != "ALL":
            clauses.append("UPPER(contents) = UPPER(:ts_type)")
            binds["ts_type"] = type_filter

        where_clause = " AND ".join(clauses)

        dba_query = f"""
            SELECT
                tablespace_name,
                block_size,
                initial_extent,
                next_extent,
                min_extents,
                max_extents,
                pct_increase,
                status,
                contents,
                logging,
                extent_management,
                allocation_type,
                segment_space_management,
                bigfile,
                encrypted
            FROM dba_tablespaces
            WHERE {where_clause}
            ORDER BY tablespace_name
        """

        user_query = f"""
            SELECT
                tablespace_name,
                block_size,
                initial_extent,
                next_extent,
                min_extents,
                max_extents,
                pct_increase,
                status,
                contents,
                logging,
                extent_management,
                allocation_type,
                segment_space_management,
                bigfile,
                'NO' as encrypted
            FROM user_tablespaces
            WHERE {where_clause}
            ORDER BY tablespace_name
        """

        rows: list[Any] = []
        try:
            cursor.execute(dba_query, binds)
            rows = cursor.fetchall()
        except oracledb.DatabaseError as exc:
            err = exc.args[0]
            if getattr(err, "code", None) == 942:
                logger.warning("Access to DBA_TABLESPACES denied, falling back to USER_TABLESPACES")
                try:
                    cursor.execute(user_query, binds)
                    rows = cursor.fetchall()
                except oracledb.DatabaseError as user_exc:
                    logger.error("Failed to query USER_TABLESPACES: {}", user_exc)
                    return {}
            else:
                logger.error("Database error querying DBA_TABLESPACES: {}", exc)
                return {}

        results: dict[str, TablespaceMetadata] = {}
        for row in rows:
            ts_name = str(row[0])
            bigfile_val = str(row[13]).upper() in ("YES", "Y", "TRUE")
            encrypted_val = str(row[14]).upper() in ("YES", "Y", "TRUE") if row[14] is not None else None

            results[ts_name] = TablespaceMetadata(
                tablespace_name=ts_name,
                block_size=int(row[1]) if row[1] is not None else 8192,
                initial_extent=int(row[2]) if row[2] is not None else None,
                next_extent=int(row[3]) if row[3] is not None else None,
                min_extents=int(row[4]) if row[4] is not None else None,
                max_extents=int(row[5]) if row[5] is not None else None,
                pct_increase=int(row[6]) if row[6] is not None else None,
                status=str(row[7]) if row[7] is not None else "ONLINE",
                contents=str(row[8]) if row[8] is not None else "PERMANENT",
                logging=str(row[9]) if row[9] is not None else "LOGGING",
                extent_management=str(row[10]) if row[10] is not None else "LOCAL",
                allocation_type=str(row[11]) if row[11] is not None else "SYSTEM",
                segment_space_management=str(row[12]) if row[12] is not None else "AUTO",
                bigfile=bigfile_val,
                encrypted=encrypted_val,
            )
        return results

    def _populate_datafiles(
        self,
        cursor: oracledb.Cursor,
        ts_dict: dict[str, TablespaceMetadata],
    ) -> None:
        """Fetch and attach data files from DBA_DATA_FILES.

        Args:
            cursor: Active database cursor.
            ts_dict: Map of tablespace name to metadata object.
        """
        if not ts_dict:
            return

        query = """
            SELECT
                tablespace_name,
                file_name,
                file_id,
                bytes,
                maxbytes,
                autoextensible,
                increment_by * (SELECT value FROM v$parameter WHERE name = 'db_block_size') as increment_bytes,
                status
            FROM dba_data_files
            ORDER BY tablespace_name, file_id
        """
        try:
            cursor.execute(query)
            for row in cursor.fetchall():
                ts_name = str(row[0])
                if ts_name not in ts_dict:
                    continue

                b = int(row[3]) if row[3] is not None else 0
                max_b = int(row[4]) if row[4] is not None else 0
                autoext = str(row[5]).upper() in ("YES", "Y", "TRUE")
                inc_b = int(row[6]) if row[6] is not None else 0
                size_mb = round(b / (1024 * 1024), 2)
                max_mb = round(max_b / (1024 * 1024), 2) if (autoext and max_b > 0) else None

                df = DataFileInfo(
                    file_name=str(row[1]),
                    file_id=int(row[2]),
                    file_bytes=b,
                    size_mb=size_mb,
                    max_bytes=max_b,
                    max_size_mb=max_mb,
                    autoextensible=autoext,
                    increment_by_bytes=inc_b,
                    status=str(row[7]) if row[7] is not None else "AVAILABLE",
                    is_tempfile=False,
                )
                ts_dict[ts_name].datafiles.append(df)
        except oracledb.DatabaseError as exc:
            logger.warning("Could not query DBA_DATA_FILES (insufficient privileges): {}", exc)

    def _populate_tempfiles(
        self,
        cursor: oracledb.Cursor,
        ts_dict: dict[str, TablespaceMetadata],
    ) -> None:
        """Fetch and attach temporary files from DBA_TEMP_FILES.

        Args:
            cursor: Active database cursor.
            ts_dict: Map of tablespace name to metadata object.
        """
        if not ts_dict:
            return

        query = """
            SELECT
                tablespace_name,
                file_name,
                file_id,
                bytes,
                maxbytes,
                autoextensible,
                increment_by * (SELECT value FROM v$parameter WHERE name = 'db_block_size') as increment_bytes,
                status
            FROM dba_temp_files
            ORDER BY tablespace_name, file_id
        """
        try:
            cursor.execute(query)
            for row in cursor.fetchall():
                ts_name = str(row[0])
                if ts_name not in ts_dict:
                    continue

                b = int(row[3]) if row[3] is not None else 0
                max_b = int(row[4]) if row[4] is not None else 0
                autoext = str(row[5]).upper() in ("YES", "Y", "TRUE")
                inc_b = int(row[6]) if row[6] is not None else 0
                size_mb = round(b / (1024 * 1024), 2)
                max_mb = round(max_b / (1024 * 1024), 2) if (autoext and max_b > 0) else None

                tf = DataFileInfo(
                    file_name=str(row[1]),
                    file_id=int(row[2]),
                    file_bytes=b,
                    size_mb=size_mb,
                    max_bytes=max_b,
                    max_size_mb=max_mb,
                    autoextensible=autoext,
                    increment_by_bytes=inc_b,
                    status=str(row[7]) if row[7] is not None else "AVAILABLE",
                    is_tempfile=True,
                )
                ts_dict[ts_name].datafiles.append(tf)
        except oracledb.DatabaseError as exc:
            logger.warning("Could not query DBA_TEMP_FILES (insufficient privileges): {}", exc)

    def generate_ddl_dbms_metadata(self, tablespace_name: str) -> str:
        """Extract tablespace DDL using DBMS_METADATA package.

        Args:
            tablespace_name: Name of the tablespace.

        Returns:
            str: Generated DDL statement.

        Raises:
            oracledb.DatabaseError: If DBMS_METADATA call fails.
        """
        with self._driver.session() as conn, conn.cursor() as cursor:
            sql = """
                    DECLARE
                        v_handle NUMBER;
                        v_ddl CLOB;
                    BEGIN
                        v_handle := DBMS_METADATA.OPEN('TABLESPACE');
                        DBMS_METADATA.SET_FILTER(v_handle, 'NAME', :ts_name);
                        DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);
                        DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'PRETTY', TRUE);
                        DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SEGMENT_ATTRIBUTES', TRUE);
                        DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'STORAGE', TRUE);
                        v_ddl := DBMS_METADATA.FETCH_CLOB(v_handle);
                        DBMS_METADATA.CLOSE(v_handle);
                        :out_ddl := v_ddl;
                    END;
                """
            out_clob = cursor.var(oracledb.CLOB)
            try:
                cursor.execute(
                    sql,
                    {
                        "ts_name": tablespace_name.upper(),
                        "out_ddl": out_clob,
                    },
                )
                clob_val = out_clob.getvalue()
                if clob_val:
                    return str(clob_val).strip()
            except oracledb.DatabaseError as exc:
                logger.debug(
                    "DBMS_METADATA fetch failed for tablespace {}: {}",
                    tablespace_name,
                    exc,
                )
                raise

            # Fallback to GET_DDL function
            fallback_sql = "SELECT DBMS_METADATA.GET_DDL('TABLESPACE', :ts_name) FROM DUAL"
            cursor.execute(fallback_sql, {"ts_name": tablespace_name.upper()})
            row = cursor.fetchone()
            if row and row[0]:
                ddl_text = str(row[0]).strip()
                if not ddl_text.endswith(";"):
                    ddl_text += ";"
                return ddl_text

            raise ValueError(f"No DDL returned for tablespace {tablespace_name}")

    def generate_ddl_synthetic(
        self,
        metadata: TablespaceMetadata,
        include_drop: bool = False,
    ) -> str:
        """Construct synthetic CREATE TABLESPACE DDL statement from metadata.

        Args:
            metadata: Populated tablespace metadata.
            include_drop: Whether to prepend DROP TABLESPACE statement.

        Returns:
            str: Synthesized DDL statement.
        """
        lines: list[str] = []

        if include_drop:
            lines.append(f"DROP TABLESPACE {metadata.tablespace_name} INCLUDING CONTENTS AND DATAFILES;")
            lines.append("")

        ts_kind = ""
        file_keyword = "DATAFILE"
        if metadata.contents.upper() == "TEMPORARY":
            ts_kind = "TEMPORARY "
            file_keyword = "TEMPFILE"
        elif metadata.contents.upper() == "UNDO":
            ts_kind = "UNDO "

        bigfile_keyword = "BIGFILE " if metadata.bigfile else ""
        create_line = f"CREATE {bigfile_keyword}{ts_kind}TABLESPACE {metadata.tablespace_name}".strip()
        lines.append(create_line)

        # File clauses
        if metadata.datafiles:
            file_specs: list[str] = []
            for df in metadata.datafiles:
                size_spec = f"'{df.file_name}' SIZE {max(int(df.size_mb), 1)}M"
                if df.autoextensible:
                    size_spec += " AUTOEXTEND ON"
                    if df.increment_by_bytes > 0:
                        inc_mb = max(int(df.increment_by_bytes / (1024 * 1024)), 1)
                        size_spec += f" NEXT {inc_mb}M"
                    if df.max_size_mb and df.max_size_mb > 0:
                        size_spec += f" MAXSIZE {int(df.max_size_mb)}M"
                    else:
                        size_spec += " MAXSIZE UNLIMITED"
                else:
                    size_spec += " AUTOEXTEND OFF"
                file_specs.append(size_spec)

            if len(file_specs) == 1:
                lines.append(f"  {file_keyword} {file_specs[0]}")
            else:
                lines.append(f"  {file_keyword}")
                for idx, spec in enumerate(file_specs):
                    sep = "," if idx < len(file_specs) - 1 else ""
                    lines.append(f"    {spec}{sep}")
        else:
            # Synthetic placeholder if datafiles view was inaccessible
            lines.append(f"  {file_keyword} '{metadata.tablespace_name.lower()}_01.dbf' SIZE 100M")

        # Block size (if non-default)
        if metadata.block_size and metadata.block_size != 8192:
            lines.append(f"  BLOCKSIZE {metadata.block_size}")

        # Logging (permanent tablespaces only)
        if metadata.contents.upper() == "PERMANENT":
            lines.append(f"  {metadata.logging.upper()}")

        # Extent management
        if metadata.extent_management.upper() == "LOCAL":
            if metadata.allocation_type.upper() == "UNIFORM":
                next_mb = max(int((metadata.next_extent or 1048576) / (1024 * 1024)), 1) if metadata.next_extent else 1
                lines.append(f"  EXTENT MANAGEMENT LOCAL UNIFORM SIZE {next_mb}M")
            else:
                lines.append("  EXTENT MANAGEMENT LOCAL AUTOALLOCATE")
        elif metadata.extent_management.upper() == "DICTIONARY":
            lines.append("  EXTENT MANAGEMENT DICTIONARY")

        # Segment space management
        if metadata.contents.upper() == "PERMANENT":
            if metadata.segment_space_management.upper() == "AUTO":
                lines.append("  SEGMENT SPACE MANAGEMENT AUTO")
            elif metadata.segment_space_management.upper() == "MANUAL":
                lines.append("  SEGMENT SPACE MANAGEMENT MANUAL")

        # Append terminating semicolon to CREATE statement
        lines[-1] += ";"

        # Read only status
        if metadata.status.upper() == "READ ONLY":
            lines.append(f"ALTER TABLESPACE {metadata.tablespace_name} READ ONLY;")

        return "\n".join(lines)

    def generate_all(
        self,
        tablespace_filter: str | None = None,
        type_filter: str | None = None,
        method: str = "auto",
        include_drop: bool = False,
    ) -> TablespaceDdlReport:
        """Generate DDL statements for all matching tablespaces.

        Args:
            tablespace_filter: Optional tablespace name filter.
            type_filter: Optional tablespace type filter (PERMANENT, TEMPORARY, UNDO, ALL).
            method: Generation method ('dbms_metadata', 'synthetic', or 'auto').
            include_drop: Whether to include DROP statements before CREATE.

        Returns:
            TablespaceDdlReport: Aggregated report of generated DDL statements.
        """
        metadata_list = self.get_tablespaces(tablespace_filter, type_filter)
        results: list[TablespaceDdlResult] = []

        for meta in metadata_list:
            ts_name = meta.tablespace_name
            ddl_text = ""
            gen_method = method

            if method in ("dbms_metadata", "auto"):
                try:
                    ddl_text = self.generate_ddl_dbms_metadata(ts_name)
                    gen_method = "DBMS_METADATA"
                    if include_drop:
                        drop_stmt = f"DROP TABLESPACE {ts_name} INCLUDING CONTENTS AND DATAFILES;\n\n"
                        ddl_text = drop_stmt + ddl_text
                except (oracledb.DatabaseError, ValueError, RuntimeError) as exc:
                    if method == "dbms_metadata":
                        logger.error(
                            "Failed to generate DDL via DBMS_METADATA for {}: {}",
                            ts_name,
                            exc,
                        )
                        ddl_text = f"-- Error generating DDL for {ts_name}: {exc}"
                        gen_method = "ERROR"
                    else:
                        logger.info(
                            "Falling back to synthetic DDL for {} due to DBMS_METADATA error: {}",
                            ts_name,
                            exc,
                        )
                        ddl_text = self.generate_ddl_synthetic(meta, include_drop=include_drop)
                        gen_method = "SYNTHETIC"
            else:
                ddl_text = self.generate_ddl_synthetic(meta, include_drop=include_drop)
                gen_method = "SYNTHETIC"

            results.append(
                TablespaceDdlResult(
                    tablespace_name=ts_name,
                    tablespace_type=meta.contents,
                    status=meta.status,
                    generation_method=gen_method,
                    ddl=ddl_text,
                    metadata=meta,
                )
            )

        now_str = datetime.now(timezone.utc).isoformat()
        return TablespaceDdlReport(
            generated_at=now_str,
            total_tablespaces=len(results),
            tablespaces=results,
        )


def format_ddl_output(report: TablespaceDdlReport, include_comments: bool = True) -> str:
    """Format the report into runnable SQL script text.

    Args:
        report: Populated tablespace DDL report.
        include_comments: Whether to include metadata header comments.

    Returns:
        str: Formatted SQL script text.
    """
    if not report.tablespaces:
        return "-- No tablespaces found matching the specified criteria.\n"

    sections: list[str] = []
    if include_comments:
        sections.append("-- ============================================================================")
        sections.append("-- Oracle Tablespace DDL Extraction Script")
        sections.append(f"-- Generated at: {report.generated_at}")
        sections.append(f"-- Total Tablespaces: {report.total_tablespaces}")
        sections.append("-- ============================================================================\n")

    for item in report.tablespaces:
        if include_comments:
            sections.append("-- ----------------------------------------------------------------------------")
            sections.append(f"-- Tablespace: {item.tablespace_name} (Type: {item.tablespace_type}, Status: {item.status}, Method: {item.generation_method})")
            sections.append("-- ----------------------------------------------------------------------------")
        sections.append(item.ddl.strip())
        sections.append("")

    return "\n".join(sections).strip() + "\n"


def parse_arguments(args: list[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        args: Command line argument list.

    Returns:
        argparse.Namespace: Parsed CLI options.
    """
    parser = argparse.ArgumentParser(
        description="Generate DDL definitions for Oracle database tablespaces.",
    )
    parser.add_argument("--host", default=os.getenv("ORACLE_HOST", "localhost"), help="Oracle host")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ORACLE_PORT", "1521")),
        help="Oracle listener port",
    )
    parser.add_argument(
        "--service-name",
        default=os.getenv("ORACLE_SERVICE_NAME"),
        help="Oracle service name",
    )
    parser.add_argument("--sid", default=os.getenv("ORACLE_SID"), help="Oracle SID")
    parser.add_argument(
        "-u",
        "--user",
        default=os.getenv("ORACLE_USER"),
        help="Oracle username",
    )
    parser.add_argument(
        "-p",
        "--password",
        default=os.getenv("ORACLE_PASSWORD"),
        help="Oracle password",
    )
    parser.add_argument(
        "--sysdba",
        action="store_true",
        default=os.getenv("ORACLE_SYSDBA", "0").lower() in ("1", "true", "yes"),
        help="Connect as SYSDBA",
    )
    parser.add_argument(
        "-t",
        "--tablespace",
        default=None,
        help="Filter by specific tablespace name",
    )
    parser.add_argument(
        "--type",
        choices=["ALL", "PERMANENT", "TEMPORARY", "UNDO"],
        default="ALL",
        help="Filter by tablespace type (default: ALL)",
    )
    parser.add_argument(
        "--method",
        choices=["auto", "dbms_metadata", "synthetic"],
        default="auto",
        help="DDL generation method (auto: DBMS_METADATA with synthetic fallback)",
    )
    parser.add_argument(
        "--include-drop",
        action="store_true",
        help="Prepend DROP TABLESPACE statement before CREATE",
    )
    parser.add_argument(
        "--no-comments",
        action="store_true",
        help="Exclude informational comments from SQL output",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["sql", "json"],
        default="sql",
        help="Output format (sql or json)",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        default=None,
        help="Write generated DDL to file instead of stdout",
    )
    return parser.parse_args(args)


def main(args: list[str] | None = None) -> int:
    """Execute the tablespace DDL generator command line interface.

    Args:
        args: Optional list of CLI arguments (defaults to sys.argv[1:]).

    Returns:
        int: Exit status code (0 for success, non-zero for error).
    """
    opts = parse_arguments(args or sys.argv[1:])

    if not opts.user or not opts.password:
        logger.error("Missing required credentials: username and password must be specified")
        return 1

    try:
        config = OracleConnectionConfig(
            hostname=opts.host,
            port=opts.port,
            service_name=opts.service_name,
            sid=opts.sid,
            username=opts.user,
            password=SecretStr(opts.password),
            is_sysdba=opts.sysdba,
        )
    except ValidationError as err:
        logger.error("Configuration validation error: {}", err)
        return 1

    driver = OracleDriver(config)
    generator = TablespaceDdlGenerator(driver)

    try:
        report = generator.generate_all(
            tablespace_filter=opts.tablespace,
            type_filter=opts.type,
            method=opts.method,
            include_drop=opts.include_drop,
        )
    except (oracledb.DatabaseError, ValueError, RuntimeError, OSError) as exc:
        logger.error("Error executing tablespace DDL generator: {}", exc)
        return 1

    output_text = ""
    if opts.format == "json":
        output_text = report.model_dump_json(indent=2)
    else:
        output_text = format_ddl_output(report, include_comments=not opts.no_comments)

    if opts.output_file:
        try:
            with open(opts.output_file, "w", encoding="utf-8") as f:
                f.write(output_text)
            logger.info("DDL output written to {}", opts.output_file)
        except OSError as err:
            logger.error("Failed to write output to {}: {}", opts.output_file, err)
            return 1
    else:
        sys.stdout.write(output_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
