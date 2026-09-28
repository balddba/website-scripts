#!/usr/bin/env python3
# ===============================================================================
#
# Script Name: tde_report.py
# Title: Oracle Transparent Data Encryption (TDE) report
# Tags: Python, Security, Encryption, TDE
# Purpose: Report on Oracle TDE configuration, keystore/wallet status, encrypted tablespaces, tables, and columns.
#
# Description:
#   Audits and reports Transparent Data Encryption (TDE) across an Oracle
#   database. Queries keystore/wallet status (GV$ENCRYPTION_WALLET), master
#   encryption keys (V$ENCRYPTION_KEYS), tablespace encryption (DBA_TABLESPACES,
#   V$ENCRYPTED_TABLESPACES), tables residing in encrypted tablespaces,
#   column-level encryption (DBA_ENCRYPTED_COLUMNS), and encrypted SecureFile
#   LOB segments (DBA_LOBS).
#
# Parameters:
#   Command-line Oracle connection settings and owner filter; use --help.
#
# Required Privileges:
#   - SELECT on GV$ENCRYPTION_WALLET (or V$ENCRYPTION_WALLET)
#   - SELECT on V$ENCRYPTION_KEYS
#   - SELECT on V$PARAMETER
#   - SELECT on DBA_TABLESPACES
#   - SELECT on V$TABLESPACE
#   - SELECT on V$ENCRYPTED_TABLESPACES
#   - SELECT on DBA_DATA_FILES and DBA_TEMP_FILES
#   - SELECT on DBA_TABLES and DBA_TAB_PARTITIONS
#   - SELECT on DBA_ENCRYPTED_COLUMNS
#   - SELECT on DBA_LOBS
#   - Or SELECT_CATALOG_ROLE / DBA
#
# Output Format:
#   - Formatted plain-text summary or JSON report written to stdout or file
#
# Example Usage:
#   python tde_report.py --help
#   python tde_report.py --host dbhost --service-name orcl --user system --password manager
#   python tde_report.py --user sys --password secret --sysdba --json
#
# Author: Aaron Myers <aaron@balddba.com>
#
# ===============================================================================
"""Audit and report Oracle Transparent Data Encryption (TDE) configuration and objects."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone

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
        owner: Optional schema owner filter.
    """

    model_config = {"extra": "forbid"}

    hostname: str = Field(default="localhost", description="Database hostname")
    port: int = Field(default=1521, description="Database port")
    service_name: str | None = Field(default=None, description="Oracle service name")
    sid: str | None = Field(default=None, description="Oracle SID")
    username: str = Field(..., description="Database username")
    password: SecretStr = Field(..., description="Database password")
    is_sysdba: bool = Field(default=False, description="Connect with SYSDBA mode")
    owner: str | None = Field(default=None, description="Schema owner filter")


class TdeParameter(BaseModel):
    """Database initialization parameter relevant to TDE.

    Attributes:
        name: Parameter name.
        value: Configured parameter value.
    """

    model_config = {"extra": "forbid"}

    name: str
    value: str | None = None


class KeystoreWallet(BaseModel):
    """Keystore wallet status record from GV$ENCRYPTION_WALLET.

    Attributes:
        inst_id: RAC instance number.
        con_id: Container ID.
        container_name: Container or PDB name.
        wrl_type: Keystore type (FILE, HSM, OKV).
        wrl_parameter: Location path or connection string.
        status: Keystore status (OPEN, CLOSED, OPEN_NO_MASTER_KEY).
        wallet_type: Wallet type (PASSWORD, AUTOLOGIN, LOCAL_AUTOLOGIN).
        wallet_order: Wallet priority order (PRIMARY, SECONDARY).
        fully_backed_up: Whether keystore has been fully backed up.
    """

    model_config = {"extra": "forbid"}

    inst_id: int
    con_id: int | None = None
    container_name: str | None = None
    wrl_type: str | None = None
    wrl_parameter: str | None = None
    status: str
    wallet_type: str | None = None
    wallet_order: str | None = None
    fully_backed_up: str | None = None


class MasterEncryptionKey(BaseModel):
    """Master encryption key record from V$ENCRYPTION_KEYS.

    Attributes:
        pdb_name: Container or PDB name.
        con_id: Container ID.
        key_id: Unique key identifier.
        key_use: Purpose of the key (e.g. TDE IN-DATABASE MASTER KEY).
        keystore_type: Type of keystore holding the key.
        creation_time: Timestamp when key was generated.
        activation_time: Timestamp when key was activated.
        tag: Optional administrative tag.
    """

    model_config = {"extra": "forbid"}

    key_id: str
    pdb_name: str | None = None
    con_id: int | None = None
    key_use: str | None = None
    keystore_type: str | None = None
    creation_time: str | None = None
    activation_time: str | None = None
    tag: str | None = None


class EncryptedTablespace(BaseModel):
    """Tablespace encryption status and metrics.

    Attributes:
        tablespace_name: Tablespace name.
        ts_type: Contents type (PERMANENT, UNDO, TEMPORARY).
        status: Tablespace status (ONLINE, READ ONLY).
        encrypted: DBA_TABLESPACES encryption flag (YES, NO).
        encryption_alg: Encryption algorithm (e.g. AES256, NONE).
        tde_status: Encryption operational state (NORMAL, UNENCRYPTED).
        size_gb: Total allocated size in gigabytes.
    """

    model_config = {"extra": "forbid"}

    tablespace_name: str
    ts_type: str
    status: str
    encrypted: str
    encryption_alg: str
    tde_status: str
    size_gb: float


class EncryptedTableSummary(BaseModel):
    """Summary of tables stored in an encrypted tablespace.

    Attributes:
        owner: Schema owner.
        tablespace_name: Encrypted tablespace name.
        table_count: Distinct tables residing in the tablespace.
        segment_count: Total segments (including partitions).
    """

    model_config = {"extra": "forbid"}

    owner: str
    tablespace_name: str
    table_count: int
    segment_count: int


class EncryptedTableDetail(BaseModel):
    """Details for a table residing in an encrypted tablespace.

    Attributes:
        owner: Schema owner.
        table_name: Table name.
        tablespace_name: Encrypted tablespace name.
        partitioned: Whether table is partitioned (YES, NO).
        num_rows: Estimated row count from statistics.
        encryption_alg: Algorithm used to encrypt the tablespace.
    """

    model_config = {"extra": "forbid"}

    owner: str
    table_name: str
    tablespace_name: str
    partitioned: str | None = None
    num_rows: int | None = None
    encryption_alg: str


class EncryptedColumn(BaseModel):
    """Column-level TDE record from DBA_ENCRYPTED_COLUMNS.

    Attributes:
        owner: Schema owner.
        table_name: Table name.
        column_name: Encrypted column name.
        encryption_alg: Encryption algorithm (e.g. AES 256 bits key).
        salt: Whether salt is enabled (YES, NO).
        integrity_alg: Integrity check algorithm (e.g. SHA-1, NOMAC).
    """

    model_config = {"extra": "forbid"}

    owner: str
    table_name: str
    column_name: str
    encryption_alg: str
    salt: str | None = None
    integrity_alg: str | None = None


class EncryptedLob(BaseModel):
    """Encrypted LOB column record from DBA_LOBS.

    Attributes:
        owner: Schema owner.
        table_name: Table name.
        column_name: LOB column name.
        tablespace_name: Storage tablespace name.
        securefile: Whether LOB is SecureFiles (YES, NO).
        encrypt: Encryption flag from DBA_LOBS (YES, NO).
    """

    model_config = {"extra": "forbid"}

    owner: str
    table_name: str
    column_name: str
    tablespace_name: str | None = None
    securefile: str | None = None
    encrypt: str


class TdeOverview(BaseModel):
    """High-level summary of TDE deployment status.

    Attributes:
        open_wallets: Number of open keystore wallets found.
        encrypted_tablespaces: Count of encrypted tablespaces.
        total_tablespaces: Count of all tablespaces.
        tables_in_encrypted_ts: Distinct tables in encrypted tablespaces.
        encrypted_columns: Count of column-level encrypted columns.
        encrypted_lobs: Count of encrypted SecureFile LOBs.
    """

    model_config = {"extra": "forbid"}

    open_wallets: int
    encrypted_tablespaces: int
    total_tablespaces: int
    tables_in_encrypted_ts: int
    encrypted_columns: int
    encrypted_lobs: int


class TdeReport(BaseModel):
    """Complete diagnostic report for Oracle TDE.

    Attributes:
        generated_at: Report generation timestamp in UTC.
        filter_owner: Schema owner filter applied, if any.
        overview: High-level TDE metric summary.
        parameters: TDE-related database initialization parameters.
        wallets: Keystore wallet records across instances.
        master_keys: Master encryption keys and activation records.
        tablespaces: Inventory of all tablespaces with encryption status.
        table_summaries: Grouped summary of tables in encrypted tablespaces.
        table_details: Detailed list of tables in encrypted tablespaces.
        columns: Detailed list of column-level encrypted columns.
        lobs: Detailed list of encrypted LOB segments.
    """

    model_config = {"extra": "forbid"}

    generated_at: str
    filter_owner: str | None = None
    overview: TdeOverview
    parameters: list[TdeParameter]
    wallets: list[KeystoreWallet]
    master_keys: list[MasterEncryptionKey]
    tablespaces: list[EncryptedTablespace]
    table_summaries: list[EncryptedTableSummary]
    table_details: list[EncryptedTableDetail]
    columns: list[EncryptedColumn]
    lobs: list[EncryptedLob]


class OracleDriver:
    """Manages connections and session lifecycle for Oracle database."""

    def __init__(self, config: OracleConnectionConfig) -> None:
        """Initialize the Oracle driver with connection settings.

        Args:
            config: Oracle connection settings and credentials.
        """
        self._config = config

    @contextmanager
    def session(self) -> Generator[oracledb.Connection, None, None]:
        """Open and yield an Oracle database connection.

        Yields:
            oracledb.Connection: Active database connection.

        Raises:
            oracledb.DatabaseError: If connection fails.
        """
        if self._config.service_name:
            dsn = oracledb.makedsn(
                self._config.hostname,
                self._config.port,
                service_name=self._config.service_name,
            )
        elif self._config.sid:
            dsn = oracledb.makedsn(
                self._config.hostname,
                self._config.port,
                sid=self._config.sid,
            )
        else:
            dsn = f"{self._config.hostname}:{self._config.port}"

        mode = oracledb.SYSDBA if (self._config.is_sysdba or self._config.username.upper() == "SYS") else 0
        password = self._config.password.get_secret_value()

        logger.bind(
            host=self._config.hostname,
            port=self._config.port,
            user=self._config.username,
        ).info("Connecting to Oracle database")

        try:
            with oracledb.connect(
                user=self._config.username,
                password=password,
                dsn=dsn,
                mode=mode,
            ) as conn:
                yield conn
        except oracledb.DatabaseError as exc:
            logger.bind(
                host=self._config.hostname,
                port=self._config.port,
                user=self._config.username,
            ).error("Database connection failed: {}", exc)
            raise


class TdeReporter:
    """Audits Oracle Transparent Data Encryption status and protected objects."""

    def __init__(self, driver: OracleDriver, owner_filter: str | None = None) -> None:
        """Initialize the TDE reporter.

        Args:
            driver: Oracle database session driver.
            owner_filter: Optional schema owner filter.
        """
        self._driver = driver
        self._owner_filter = owner_filter.upper() if owner_filter else None

    def generate_report(self) -> TdeReport:
        """Execute queries and compile the full TDE report.

        Returns:
            TdeReport: Complete structured TDE report.
        """
        with self._driver.session() as conn:
            parameters = self._fetch_parameters(conn)
            wallets = self._fetch_wallets(conn)
            master_keys = self._fetch_master_keys(conn)
            tablespaces = self._fetch_tablespaces(conn)
            table_summaries = self._fetch_table_summaries(conn)
            table_details = self._fetch_table_details(conn)
            columns = self._fetch_columns(conn)
            lobs = self._fetch_lobs(conn)

        overview = TdeOverview(
            open_wallets=sum(1 for w in wallets if w.status == "OPEN"),
            encrypted_tablespaces=sum(1 for t in tablespaces if t.encrypted == "YES"),
            total_tablespaces=len(tablespaces),
            tables_in_encrypted_ts=len({(t.owner, t.table_name) for t in table_details}),
            encrypted_columns=len(columns),
            encrypted_lobs=len(lobs),
        )

        return TdeReport(
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            filter_owner=self._owner_filter,
            overview=overview,
            parameters=parameters,
            wallets=wallets,
            master_keys=master_keys,
            tablespaces=tablespaces,
            table_summaries=table_summaries,
            table_details=table_details,
            columns=columns,
            lobs=lobs,
        )

    def _fetch_parameters(self, conn: oracledb.Connection) -> list[TdeParameter]:
        """Fetch TDE-related configuration parameters from V$PARAMETER.

        Args:
            conn: Active Oracle connection.

        Returns:
            list[TdeParameter]: Initialization parameters.
        """
        sql = """
            SELECT name, value
            FROM v$parameter
            WHERE name IN ('encrypt_new_tablespaces', 'wallet_root', 'tde_configuration')
            ORDER BY name
        """
        results: list[TdeParameter] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                for row in cur:
                    results.append(TdeParameter(name=str(row[0]), value=str(row[1]) if row[1] is not None else None))
        except oracledb.DatabaseError as exc:
            logger.warning("Could not query V$PARAMETER: {}", exc)
        return results

    def _fetch_wallets(self, conn: oracledb.Connection) -> list[KeystoreWallet]:
        """Fetch keystore wallet status from GV$ENCRYPTION_WALLET.

        Args:
            conn: Active Oracle connection.

        Returns:
            list[KeystoreWallet]: Keystore wallet records.
        """
        sql = """
            SELECT
                w.inst_id,
                w.con_id,
                NVL(c.name, CASE WHEN w.con_id = 1 THEN 'CDB$ROOT' WHEN w.con_id = 0 THEN 'DATABASE' ELSE 'CON_ID ' || TO_CHAR(w.con_id) END),
                w.wrl_type,
                w.wrl_parameter,
                w.status,
                w.wallet_type,
                w.wallet_order,
                w.fully_backed_up
            FROM gv$encryption_wallet w
            LEFT JOIN v$containers c ON w.con_id = c.con_id
            ORDER BY w.con_id, w.inst_id, w.wallet_order
        """
        results: list[KeystoreWallet] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                for row in cur:
                    results.append(
                        KeystoreWallet(
                            inst_id=int(row[0]),
                            con_id=int(row[1]) if row[1] is not None else None,
                            container_name=str(row[2]) if row[2] is not None else None,
                            wrl_type=str(row[3]) if row[3] is not None else None,
                            wrl_parameter=str(row[4]) if row[4] is not None else None,
                            status=str(row[5]),
                            wallet_type=str(row[6]) if row[6] is not None else None,
                            wallet_order=str(row[7]) if row[7] is not None else None,
                            fully_backed_up=str(row[8]) if row[8] is not None else None,
                        )
                    )
        except oracledb.DatabaseError as exc:
            logger.warning("Could not query GV$ENCRYPTION_WALLET: {}", exc)
        return results

    def _fetch_master_keys(self, conn: oracledb.Connection) -> list[MasterEncryptionKey]:
        """Fetch master encryption keys from V$ENCRYPTION_KEYS.

        Args:
            conn: Active Oracle connection.

        Returns:
            list[MasterEncryptionKey]: Master key records.
        """
        sql = """
            SELECT
                NVL(k.activating_pdbname, NVL(k.creator_pdbname, NVL(c.name, 'CDB$ROOT'))),
                k.con_id,
                k.key_id,
                k.key_use,
                k.keystore_type,
                TO_CHAR(k.creation_time, 'YYYY-MM-DD HH24:MI:SS'),
                TO_CHAR(k.activation_time, 'YYYY-MM-DD HH24:MI:SS'),
                k.tag
            FROM v$encryption_keys k
            LEFT JOIN v$containers c ON k.con_id = c.con_id
            ORDER BY k.con_id, k.activation_time DESC NULLS LAST
        """
        results: list[MasterEncryptionKey] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                for row in cur:
                    results.append(
                        MasterEncryptionKey(
                            pdb_name=str(row[0]),
                            con_id=int(row[1]) if row[1] is not None else None,
                            key_id=str(row[2]),
                            key_use=str(row[3]) if row[3] is not None else None,
                            keystore_type=str(row[4]) if row[4] is not None else None,
                            creation_time=str(row[5]) if row[5] is not None else None,
                            activation_time=str(row[6]) if row[6] is not None else None,
                            tag=str(row[7]) if row[7] is not None else None,
                        )
                    )
        except oracledb.DatabaseError as exc:
            logger.warning("Could not query V$ENCRYPTION_KEYS: {}", exc)
        return results

    def _fetch_tablespaces(self, conn: oracledb.Connection) -> list[EncryptedTablespace]:
        """Fetch tablespace inventory with encryption status.

        Args:
            conn: Active Oracle connection.

        Returns:
            list[EncryptedTablespace]: Tablespace encryption metrics.
        """
        sql = """
            SELECT
                t.tablespace_name,
                t.contents AS ts_type,
                t.status AS ts_status,
                t.encrypted,
                NVL(e.encryptionalg, 'NONE') AS encryption_alg,
                NVL(e.status, 'UNENCRYPTED') AS tde_status,
                ROUND(NVL(SUM(f.bytes), 0) / 1024 / 1024 / 1024, 2) AS size_gb
            FROM dba_tablespaces t
            LEFT JOIN v$tablespace vt ON t.tablespace_name = vt.name
            LEFT JOIN v$encrypted_tablespaces e ON vt.ts# = e.ts#
            LEFT JOIN (
                SELECT tablespace_name, bytes FROM dba_data_files
                UNION ALL
                SELECT tablespace_name, bytes FROM dba_temp_files
            ) f ON t.tablespace_name = f.tablespace_name
            GROUP BY
                t.tablespace_name,
                t.contents,
                t.status,
                t.encrypted,
                e.encryptionalg,
                e.status
            ORDER BY
                CASE WHEN t.encrypted = 'YES' THEN 1 ELSE 2 END,
                t.tablespace_name
        """
        results: list[EncryptedTablespace] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                for row in cur:
                    results.append(
                        EncryptedTablespace(
                            tablespace_name=str(row[0]),
                            ts_type=str(row[1]),
                            status=str(row[2]),
                            encrypted=str(row[3]),
                            encryption_alg=str(row[4]),
                            tde_status=str(row[5]),
                            size_gb=float(row[6]) if row[6] is not None else 0.0,
                        )
                    )
        except oracledb.DatabaseError as exc:
            logger.warning("Could not query tablespaces: {}", exc)
        return results

    def _fetch_table_summaries(self, conn: oracledb.Connection) -> list[EncryptedTableSummary]:
        """Fetch table counts in encrypted tablespaces grouped by owner.

        Args:
            conn: Active Oracle connection.

        Returns:
            list[EncryptedTableSummary]: Summary counts by owner and tablespace.
        """
        sql = """
            SELECT
                obj.owner,
                obj.tablespace_name,
                COUNT(DISTINCT obj.table_name) AS table_count,
                COUNT(*) AS segment_count
            FROM (
                SELECT t.owner, t.table_name, t.tablespace_name
                FROM dba_tables t
                JOIN dba_tablespaces ts ON t.tablespace_name = ts.tablespace_name
                WHERE ts.encrypted = 'YES'
                  AND (:owner IS NULL OR t.owner = :owner)
                UNION ALL
                SELECT p.table_owner AS owner, p.table_name, p.tablespace_name
                FROM dba_tab_partitions p
                JOIN dba_tablespaces ts ON p.tablespace_name = ts.tablespace_name
                WHERE ts.encrypted = 'YES'
                  AND (:owner IS NULL OR p.table_owner = :owner)
            ) obj
            GROUP BY obj.owner, obj.tablespace_name
            ORDER BY obj.owner, obj.tablespace_name
        """
        results: list[EncryptedTableSummary] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql, [self._owner_filter])
                for row in cur:
                    results.append(
                        EncryptedTableSummary(
                            owner=str(row[0]),
                            tablespace_name=str(row[1]),
                            table_count=int(row[2]),
                            segment_count=int(row[3]),
                        )
                    )
        except oracledb.DatabaseError as exc:
            logger.warning("Could not query table summaries: {}", exc)
        return results

    def _fetch_table_details(self, conn: oracledb.Connection) -> list[EncryptedTableDetail]:
        """Fetch detailed list of tables residing in encrypted tablespaces.

        Args:
            conn: Active Oracle connection.

        Returns:
            list[EncryptedTableDetail]: Individual encrypted tables.
        """
        sql = """
            SELECT
                t.owner,
                t.table_name,
                t.tablespace_name,
                t.partitioned,
                t.num_rows,
                NVL(e.encryptionalg, 'ENCRYPTED') AS encryption_alg
            FROM dba_tables t
            JOIN dba_tablespaces ts ON t.tablespace_name = ts.tablespace_name
            LEFT JOIN v$tablespace vt ON ts.tablespace_name = vt.name
            LEFT JOIN v$encrypted_tablespaces e ON vt.ts# = e.ts#
            WHERE ts.encrypted = 'YES'
              AND (:owner IS NULL OR t.owner = :owner)
            ORDER BY t.owner, t.table_name
        """
        results: list[EncryptedTableDetail] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql, [self._owner_filter])
                for row in cur:
                    results.append(
                        EncryptedTableDetail(
                            owner=str(row[0]),
                            table_name=str(row[1]),
                            tablespace_name=str(row[2]),
                            partitioned=str(row[3]) if row[3] is not None else None,
                            num_rows=int(row[4]) if row[4] is not None else None,
                            encryption_alg=str(row[5]),
                        )
                    )
        except oracledb.DatabaseError as exc:
            logger.warning("Could not query table details: {}", exc)
        return results

    def _fetch_columns(self, conn: oracledb.Connection) -> list[EncryptedColumn]:
        """Fetch column-level encryption records from DBA_ENCRYPTED_COLUMNS.

        Args:
            conn: Active Oracle connection.

        Returns:
            list[EncryptedColumn]: Encrypted column records.
        """
        sql = """
            SELECT
                e.owner,
                e.table_name,
                e.column_name,
                e.encryption_alg,
                e.salt,
                e.integrity_alg
            FROM dba_encrypted_columns e
            WHERE (:owner IS NULL OR e.owner = :owner)
            ORDER BY e.owner, e.table_name, e.column_name
        """
        results: list[EncryptedColumn] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql, [self._owner_filter])
                for row in cur:
                    results.append(
                        EncryptedColumn(
                            owner=str(row[0]),
                            table_name=str(row[1]),
                            column_name=str(row[2]),
                            encryption_alg=str(row[3]),
                            salt=str(row[4]) if row[4] is not None else None,
                            integrity_alg=str(row[5]) if row[5] is not None else None,
                        )
                    )
        except oracledb.DatabaseError as exc:
            logger.warning("Could not query DBA_ENCRYPTED_COLUMNS: {}", exc)
        return results

    def _fetch_lobs(self, conn: oracledb.Connection) -> list[EncryptedLob]:
        """Fetch encrypted LOB column records from DBA_LOBS.

        Args:
            conn: Active Oracle connection.

        Returns:
            list[EncryptedLob]: Encrypted LOB records.
        """
        sql = """
            SELECT
                l.owner,
                l.table_name,
                l.column_name,
                l.tablespace_name,
                l.securefile,
                l.encrypt
            FROM dba_lobs l
            WHERE l.encrypt = 'YES'
              AND (:owner IS NULL OR l.owner = :owner)
            ORDER BY l.owner, l.table_name, l.column_name
        """
        results: list[EncryptedLob] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql, [self._owner_filter])
                for row in cur:
                    results.append(
                        EncryptedLob(
                            owner=str(row[0]),
                            table_name=str(row[1]),
                            column_name=str(row[2]),
                            tablespace_name=str(row[3]) if row[3] is not None else None,
                            securefile=str(row[4]) if row[4] is not None else None,
                            encrypt=str(row[5]),
                        )
                    )
        except oracledb.DatabaseError as exc:
            logger.warning("Could not query DBA_LOBS: {}", exc)
        return results


def format_report_text(report: TdeReport) -> str:
    """Format the TDE report into human-readable plain text.

    Args:
        report: Structured TDE report data.

    Returns:
        str: Formatted report text.
    """
    lines: list[str] = [
        "=" * 80,
        "Oracle Transparent Data Encryption (TDE) Report",
        f"Generated At : {report.generated_at}",
        f"Schema Filter: {report.filter_owner or 'ALL SCHEMAS'}",
        "=" * 80,
        "",
        "--- 1. OVERALL TDE SUMMARY ---",
        f"Open Wallets             : {report.overview.open_wallets}",
        f"Encrypted Tablespaces    : {report.overview.encrypted_tablespaces} / {report.overview.total_tablespaces}",
        f"Tables in Encrypted TS   : {report.overview.tables_in_encrypted_ts}",
        f"Column-Level Encrypted   : {report.overview.encrypted_columns}",
        f"Encrypted SecureFile LOBs: {report.overview.encrypted_lobs}",
        "",
    ]

    # Parameters
    lines.append("--- 2. TDE CONFIGURATION PARAMETERS ---")
    if report.parameters:
        lines.append(f"{'Parameter':<32} {'Value':<45}")
        lines.append(f"{'-' * 32} {'-' * 45}")
        for param in report.parameters:
            lines.append(f"{param.name:<32} {param.value or '(null)':<45}")
    else:
        lines.append("No TDE initialization parameters found.")
    lines.append("")

    # Wallets
    lines.append("--- 3. KEYSTORE / WALLET STATUS (GV$ENCRYPTION_WALLET) ---")
    if report.wallets:
        lines.append(f"{'Inst':<5} {'Con':<5} {'Container / PDB':<20} {'Type':<8} {'Status':<16} {'Wallet Type':<16} {'Backed Up':<10} {'Location'}")
        lines.append(f"{'-' * 5} {'-' * 5} {'-' * 20} {'-' * 8} {'-' * 16} {'-' * 16} {'-' * 10} {'-' * 20}")
        for w in report.wallets:
            con_str = str(w.con_id) if w.con_id is not None else "-"
            lines.append(f"{w.inst_id:<5} {con_str:<5} {w.container_name or '':<20} {w.wrl_type or '':<8} {w.status:<16} {w.wallet_type or '':<16} {w.fully_backed_up or '':<10} {w.wrl_parameter or ''}")
    else:
        lines.append("No keystore wallet records returned (TDE may not be configured).")
    lines.append("")

    # Master Keys
    lines.append("--- 4. MASTER ENCRYPTION KEYS (V$ENCRYPTION_KEYS) ---")
    if report.master_keys:
        lines.append(f"{'Container / PDB':<18} {'Con':<5} {'Key ID Prefix':<32} {'Key Use':<24} {'Activated':<20} {'Tag'}")
        lines.append(f"{'-' * 18} {'-' * 5} {'-' * 32} {'-' * 24} {'-' * 20} {'-' * 10}")
        for k in report.master_keys:
            con_str = str(k.con_id) if k.con_id is not None else "-"
            key_id_disp = k.key_id[:30] + ".." if len(k.key_id) > 32 else k.key_id
            lines.append(f"{k.pdb_name or 'CDB$ROOT':<18} {con_str:<5} {key_id_disp:<32} {k.key_use or '':<24} {k.activation_time or '':<20} {k.tag or ''}")
    else:
        lines.append("No master encryption keys found.")
    lines.append("")

    # Tablespaces
    lines.append("--- 5. TABLESPACES ENCRYPTION STATUS ---")
    if report.tablespaces:
        lines.append(f"{'Tablespace':<24} {'Type':<11} {'Status':<10} {'Encrypted':<10} {'Algorithm':<12} {'Size GB':>10}")
        lines.append(f"{'-' * 24} {'-' * 11} {'-' * 10} {'-' * 10} {'-' * 12} {'-' * 10}")
        for ts in report.tablespaces:
            lines.append(f"{ts.tablespace_name:<24} {ts.ts_type:<11} {ts.status:<10} {ts.encrypted:<10} {ts.encryption_alg:<12} {ts.size_gb:>10.2f}")
    else:
        lines.append("No tablespace records found.")
    lines.append("")

    # Tables in Encrypted Tablespaces Summary
    lines.append("--- 6. TABLES IN ENCRYPTED TABLESPACES (SUMMARY BY OWNER) ---")
    if report.table_summaries:
        lines.append(f"{'Owner':<20} {'Tablespace':<24} {'Table Count':>12} {'Segment Count':>14}")
        lines.append(f"{'-' * 20} {'-' * 24} {'-' * 12} {'-' * 14}")
        for s in report.table_summaries:
            lines.append(f"{s.owner:<20} {s.tablespace_name:<24} {s.table_count:>12} {s.segment_count:>14}")
    else:
        lines.append("No tables found in encrypted tablespaces.")
    lines.append("")

    # Tables Detail
    lines.append("--- 7. TABLES IN ENCRYPTED TABLESPACES (DETAIL) ---")
    if report.table_details:
        lines.append(f"{'Owner':<20} {'Table Name':<28} {'Tablespace':<22} {'Partitioned':<12} {'Num Rows':>12}")
        lines.append(f"{'-' * 20} {'-' * 28} {'-' * 22} {'-' * 12} {'-' * 12}")
        for td in report.table_details:
            rows_str = str(td.num_rows) if td.num_rows is not None else "-"
            lines.append(f"{td.owner:<20} {td.table_name:<28} {td.tablespace_name:<22} {td.partitioned or 'NO':<12} {rows_str:>12}")
    else:
        lines.append("No tables found in encrypted tablespaces.")
    lines.append("")

    # Column-level encryption
    lines.append("--- 8. COLUMN-LEVEL ENCRYPTION (DBA_ENCRYPTED_COLUMNS) ---")
    if report.columns:
        lines.append(f"{'Owner':<20} {'Table Name':<26} {'Column Name':<24} {'Algorithm':<20} {'Salt':<6} {'Integrity'}")
        lines.append(f"{'-' * 20} {'-' * 26} {'-' * 24} {'-' * 20} {'-' * 6} {'-' * 10}")
        for c in report.columns:
            lines.append(f"{c.owner:<20} {c.table_name:<26} {c.column_name:<24} {c.encryption_alg:<20} {c.salt or 'NO':<6} {c.integrity_alg or ''}")
    else:
        lines.append("No column-level encryption found.")
    lines.append("")

    # Encrypted LOBs
    lines.append("--- 9. ENCRYPTED LOB SEGMENTS (DBA_LOBS) ---")
    if report.lobs:
        lines.append(f"{'Owner':<20} {'Table Name':<26} {'Column Name':<24} {'Tablespace':<20} {'SecureFile':<11} {'Encrypt'}")
        lines.append(f"{'-' * 20} {'-' * 26} {'-' * 24} {'-' * 20} {'-' * 11} {'-' * 8}")
        for lob in report.lobs:
            lines.append(f"{lob.owner:<20} {lob.table_name:<26} {lob.column_name:<24} {lob.tablespace_name or '':<20} {lob.securefile or 'NO':<11} {lob.encrypt}")
    else:
        lines.append("No encrypted LOB segments found.")
    lines.append("")

    return "\n".join(lines)


def format_report_json(report: TdeReport) -> str:
    """Format the TDE report as JSON.

    Args:
        report: Structured TDE report data.

    Returns:
        str: JSON-encoded report text.
    """
    return report.model_dump_json(indent=2)


def build_arg_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser.

    Returns:
        argparse.ArgumentParser: Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description="Audit and report Oracle Transparent Data Encryption (TDE) status and objects.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    conn_group = parser.add_argument_group("Oracle Connection")
    conn_group.add_argument(
        "--host",
        dest="hostname",
        default=os.getenv("ORACLE_HOST", "localhost"),
        help="Database hostname or IP (default: localhost / $ORACLE_HOST)",
    )
    conn_group.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ORACLE_PORT", "1521")),
        help="Database listener port (default: 1521 / $ORACLE_PORT)",
    )
    conn_group.add_argument(
        "--service-name",
        dest="service_name",
        default=os.getenv("ORACLE_SERVICE_NAME"),
        help="Oracle service name (e.g. ORCLPDB1 / $ORACLE_SERVICE_NAME)",
    )
    conn_group.add_argument(
        "--sid",
        default=os.getenv("ORACLE_SID"),
        help="Oracle SID (e.g. ORCL / $ORACLE_SID)",
    )
    conn_group.add_argument(
        "-u",
        "--user",
        dest="username",
        default=os.getenv("ORACLE_USER"),
        help="Database username ($ORACLE_USER)",
    )
    conn_group.add_argument(
        "-p",
        "--password",
        default=os.getenv("ORACLE_PASSWORD"),
        help="Database password ($ORACLE_PASSWORD)",
    )
    conn_group.add_argument(
        "--sysdba",
        action="store_true",
        default=os.getenv("ORACLE_SYSDBA", "").lower() in ("1", "true", "yes"),
        help="Connect with SYSDBA administrative privilege",
    )

    filter_group = parser.add_argument_group("Report Filters")
    filter_group.add_argument(
        "--owner",
        help="Filter tables and columns by schema owner (e.g. HR)",
    )

    out_group = parser.add_argument_group("Output Options")
    out_group.add_argument(
        "--json",
        action="store_true",
        help="Output report in JSON format",
    )
    out_group.add_argument(
        "-o",
        "--output",
        help="Save report output to specified file path",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute the CLI application.

    Args:
        argv: Optional list of command-line arguments.

    Returns:
        int: Exit status code (0 for success, non-zero for failure).
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not args.username:
        logger.error("Missing database username. Provide via --user or $ORACLE_USER.")
        return 1

    if not args.password:
        logger.error("Missing database password. Provide via --password or $ORACLE_PASSWORD.")
        return 1

    try:
        config = OracleConnectionConfig(
            hostname=args.hostname,
            port=args.port,
            service_name=args.service_name,
            sid=args.sid,
            username=args.username,
            password=SecretStr(args.password),
            is_sysdba=args.sysdba,
            owner=args.owner,
        )
    except ValidationError as exc:
        logger.error("Invalid configuration: {}", exc)
        return 1

    driver = OracleDriver(config)
    reporter = TdeReporter(driver, owner_filter=config.owner)

    try:
        report = reporter.generate_report()
    except oracledb.DatabaseError as exc:
        logger.error("Failed to generate TDE report: {}", exc)
        return 2

    output_text = format_report_json(report) if args.json else format_report_text(report)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_text + "\n")
            logger.info("Report saved to {}", args.output)
        except OSError as exc:
            logger.error("Could not write to output file {}: {}", args.output, exc)
            return 3
    else:
        sys.stdout.write(output_text + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
