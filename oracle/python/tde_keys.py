#!/usr/bin/env python3
# ===============================================================================
#
# Script Name: tde_keys.py
# Title: Oracle TDE encryption key information
# Tags: Python, Security, Encryption, TDE, Keys, Multitenant, PDB
# Purpose: Report on Oracle TDE master encryption keys, keystore status, key history, and backup state across CDB and PDBs.
#
# Description:
#   Audits Transparent Data Encryption (TDE) master keys and keystore health
#   across an Oracle database. In Multitenant environments, it reports keys,
#   wallets, and tablespace encryptions for CDB$ROOT and all pluggable databases.
#   Queries keystore/wallet configuration and open state (GV$ENCRYPTION_WALLET),
#   currently active master encryption keys per PDB with activation age and
#   backup status, full key lifecycle and rekey history per PDB (V$ENCRYPTION_KEYS),
#   tablespace encryption key mapping per container (V$ENCRYPTED_TABLESPACES),
#   and key backup and security health checks.
#
# Parameters:
#   Command-line Oracle connection settings; use --help.
#
# Required Privileges:
#   - SELECT on GV$ENCRYPTION_WALLET (or V$ENCRYPTION_WALLET)
#   - SELECT on V$ENCRYPTION_KEYS
#   - SELECT on V$ENCRYPTED_TABLESPACES
#   - SELECT on V$TABLESPACE
#   - SELECT on V$CONTAINERS
#   - Or SELECT_CATALOG_ROLE / DBA
#
# Output Format:
#   - Formatted plain-text summary or JSON report written to stdout or file
#
# Example Usage:
#   python tde_keys.py --help
#   python tde_keys.py --host dbhost --service-name orcl --user system --password manager
#   python tde_keys.py --user sys --password secret --sysdba --json
#
# Author: Aaron Myers <aaron@balddba.com>
#
# ===============================================================================
"""Audit and report Oracle Transparent Data Encryption (TDE) keys and keystores."""

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
        username: Database username.
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


class KeystoreWallet(BaseModel):
    """Keystore wallet status record from GV$ENCRYPTION_WALLET.

    Attributes:
        inst_id: RAC instance number.
        con_id: Container ID.
        container_name: Container or PDB name.
        wrl_type: Keystore type (FILE, HSM, OKV).
        wrl_parameter: Keystore location path or connection string.
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


class ActiveMasterKey(BaseModel):
    """Currently active master encryption key record.

    Attributes:
        pdb_name: Pluggable database or container name.
        con_id: Container ID.
        key_id: Unique key identifier.
        key_use: Purpose of the key (e.g. TDE IN-DATABASE MASTER KEY).
        keystore_type: Type of keystore holding the key.
        activated_time: Timestamp when key was activated.
        age_days: Age in days since activation.
        backed_up: Whether key has been backed up in the keystore.
        tag: Optional administrative tag.
    """

    model_config = {"extra": "forbid"}

    pdb_name: str
    con_id: int | None = None
    key_id: str
    key_use: str | None = None
    keystore_type: str | None = None
    activated_time: str | None = None
    age_days: float | None = None
    backed_up: str | None = None
    tag: str | None = None


class KeyLifecycleRecord(BaseModel):
    """Key lifecycle record from V$ENCRYPTION_KEYS.

    Attributes:
        pdb_name: Pluggable database or container name.
        con_id: Container ID.
        key_id: Full key identifier.
        key_id_prefix: Shortened key prefix for display.
        key_status: Lifecycle status (ACTIVE (CURRENT), RETIRED, PENDING).
        key_use: Purpose of the key.
        keystore_type: Keystore type.
        created_time: Creation timestamp.
        activated_time: Activation timestamp.
        backed_up: Backup status (YES, NO).
        tag: Administrative tag.
    """

    model_config = {"extra": "forbid"}

    pdb_name: str
    con_id: int | None = None
    key_id: str
    key_id_prefix: str
    key_status: str
    key_use: str | None = None
    keystore_type: str | None = None
    created_time: str | None = None
    activated_time: str | None = None
    backed_up: str | None = None
    tag: str | None = None


class TablespaceKeyRecord(BaseModel):
    """Mapping between tablespace and its encryption key status.

    Attributes:
        pdb_name: Pluggable database or container name.
        tablespace_name: Tablespace name.
        encryption_alg: Encryption algorithm (e.g. AES256).
        key_status: Operational key status (e.g. NORMAL).
        encrypted_key_state: Whether encrypted key is present (PRESENT, NONE).
    """

    model_config = {"extra": "forbid"}

    pdb_name: str | None = None
    tablespace_name: str
    encryption_alg: str
    key_status: str
    encrypted_key_state: str


class KeyHealthCheck(BaseModel):
    """Security and backup health check item.

    Attributes:
        check_name: Name of the check performed.
        status: Evaluation status (OK, WARNING, CRITICAL, INFO).
        details: Diagnostic details and remediation advice.
    """

    model_config = {"extra": "forbid"}

    check_name: str
    status: str
    details: str


class TdeKeyReport(BaseModel):
    """Complete diagnostic report for TDE encryption keys.

    Attributes:
        generated_at: Report generation timestamp in UTC.
        wallets: Keystore wallet records across instances and PDBs.
        active_keys: Currently active master encryption keys per PDB.
        key_history: Complete key lifecycle and rekey records per PDB.
        tablespace_keys: Tablespace encryption key mappings.
        health_checks: Security and backup health evaluations.
    """

    model_config = {"extra": "forbid"}

    generated_at: str
    wallets: list[KeystoreWallet]
    active_keys: list[ActiveMasterKey]
    key_history: list[KeyLifecycleRecord]
    tablespace_keys: list[TablespaceKeyRecord]
    health_checks: list[KeyHealthCheck]


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


class TdeKeyReporter:
    """Audits Oracle Transparent Data Encryption keys and keystores across CDB and PDBs."""

    def __init__(self, driver: OracleDriver) -> None:
        """Initialize the TDE key reporter.

        Args:
            driver: Oracle database session driver.
        """
        self._driver = driver

    def generate_report(self) -> TdeKeyReport:
        """Execute queries and compile the full TDE key report.

        Returns:
            TdeKeyReport: Complete structured key report.
        """
        with self._driver.session() as conn:
            wallets = self._fetch_wallets(conn)
            active_keys = self._fetch_active_keys(conn)
            key_history = self._fetch_key_history(conn)
            tablespace_keys = self._fetch_tablespace_keys(conn)
            health_checks = self._fetch_health_checks(conn)

        return TdeKeyReport(
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            wallets=wallets,
            active_keys=active_keys,
            key_history=key_history,
            tablespace_keys=tablespace_keys,
            health_checks=health_checks,
        )

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

    def _fetch_active_keys(self, conn: oracledb.Connection) -> list[ActiveMasterKey]:
        """Fetch currently active master encryption keys per PDB / container.

        Args:
            conn: Active Oracle connection.

        Returns:
            list[ActiveMasterKey]: Active master key records.
        """
        sql = """
            SELECT
                NVL(k.activating_pdbname, NVL(k.creator_pdbname, NVL(c.name, 'CDB$ROOT'))),
                k.con_id,
                k.key_id,
                k.key_use,
                k.keystore_type,
                TO_CHAR(k.activation_time, 'YYYY-MM-DD HH24:MI:SS'),
                ROUND(SYSDATE - CAST(k.activation_time AS DATE), 1),
                k.backed_up,
                NVL(k.tag, '(none)')
            FROM (
                SELECT
                    activating_pdbname,
                    creator_pdbname,
                    con_id,
                    key_id,
                    key_use,
                    keystore_type,
                    activation_time,
                    backed_up,
                    tag,
                    ROW_NUMBER() OVER (
                        PARTITION BY con_id, key_use
                        ORDER BY activation_time DESC NULLS LAST
                    ) AS rn
                FROM v$encryption_keys
                WHERE activation_time IS NOT NULL
            ) k
            LEFT JOIN v$containers c ON k.con_id = c.con_id
            WHERE k.rn = 1
            ORDER BY k.con_id, k.key_use
        """
        results: list[ActiveMasterKey] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                for row in cur:
                    results.append(
                        ActiveMasterKey(
                            pdb_name=str(row[0]),
                            con_id=int(row[1]) if row[1] is not None else None,
                            key_id=str(row[2]),
                            key_use=str(row[3]) if row[3] is not None else None,
                            keystore_type=str(row[4]) if row[4] is not None else None,
                            activated_time=str(row[5]) if row[5] is not None else None,
                            age_days=float(row[6]) if row[6] is not None else None,
                            backed_up=str(row[7]) if row[7] is not None else None,
                            tag=str(row[8]) if row[8] is not None else None,
                        )
                    )
        except oracledb.DatabaseError as exc:
            logger.warning("Could not query active keys: {}", exc)
        return results

    def _fetch_key_history(self, conn: oracledb.Connection) -> list[KeyLifecycleRecord]:
        """Fetch complete key history and lifecycle from V$ENCRYPTION_KEYS.

        Args:
            conn: Active Oracle connection.

        Returns:
            list[KeyLifecycleRecord]: Key lifecycle records.
        """
        sql = """
            SELECT
                NVL(k.activating_pdbname, NVL(k.creator_pdbname, NVL(c.name, 'CDB$ROOT'))),
                k.con_id,
                k.key_id,
                SUBSTR(k.key_id, 1, 30),
                CASE
                    WHEN k.activation_time = MAX(k.activation_time) OVER (PARTITION BY k.con_id, k.key_use) THEN 'ACTIVE (CURRENT)'
                    WHEN k.activation_time IS NOT NULL THEN 'RETIRED'
                    ELSE 'PENDING'
                END,
                k.key_use,
                k.keystore_type,
                TO_CHAR(k.creation_time, 'YYYY-MM-DD HH24:MI:SS'),
                TO_CHAR(k.activation_time, 'YYYY-MM-DD HH24:MI:SS'),
                k.backed_up,
                k.tag
            FROM v$encryption_keys k
            LEFT JOIN v$containers c ON k.con_id = c.con_id
            ORDER BY k.con_id, k.activation_time DESC NULLS LAST, k.creation_time DESC
        """
        results: list[KeyLifecycleRecord] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                for row in cur:
                    results.append(
                        KeyLifecycleRecord(
                            pdb_name=str(row[0]),
                            con_id=int(row[1]) if row[1] is not None else None,
                            key_id=str(row[2]),
                            key_id_prefix=str(row[3]),
                            key_status=str(row[4]),
                            key_use=str(row[5]) if row[5] is not None else None,
                            keystore_type=str(row[6]) if row[6] is not None else None,
                            created_time=str(row[7]) if row[7] is not None else None,
                            activated_time=str(row[8]) if row[8] is not None else None,
                            backed_up=str(row[9]) if row[9] is not None else None,
                            tag=str(row[10]) if row[10] is not None else None,
                        )
                    )
        except oracledb.DatabaseError as exc:
            logger.warning("Could not query V$ENCRYPTION_KEYS history: {}", exc)
        return results

    def _fetch_tablespace_keys(self, conn: oracledb.Connection) -> list[TablespaceKeyRecord]:
        """Fetch tablespace encryption key mapping from V$ENCRYPTED_TABLESPACES.

        Args:
            conn: Active Oracle connection.

        Returns:
            list[TablespaceKeyRecord]: Tablespace key mapping records.
        """
        sql = """
            SELECT
                NVL(c.name, 'CDB$ROOT'),
                vt.name,
                e.encryptionalg,
                e.status,
                CASE
                    WHEN e.encrypted_key IS NOT NULL THEN 'PRESENT'
                    ELSE 'NONE'
                END
            FROM v$encrypted_tablespaces e
            JOIN v$tablespace vt ON e.ts# = vt.ts# AND e.con_id = vt.con_id
            LEFT JOIN v$containers c ON e.con_id = c.con_id
            ORDER BY e.con_id, vt.name
        """
        results: list[TablespaceKeyRecord] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                for row in cur:
                    results.append(
                        TablespaceKeyRecord(
                            pdb_name=str(row[0]),
                            tablespace_name=str(row[1]),
                            encryption_alg=str(row[2]),
                            key_status=str(row[3]),
                            encrypted_key_state=str(row[4]),
                        )
                    )
        except oracledb.DatabaseError as exc:
            logger.warning("Could not query V$ENCRYPTED_TABLESPACES: {}", exc)
        return results

    def _fetch_health_checks(self, conn: oracledb.Connection) -> list[KeyHealthCheck]:
        """Evaluate key management and backup health checks.

        Args:
            conn: Active Oracle connection.

        Returns:
            list[KeyHealthCheck]: Health evaluation results.
        """
        sql = """
            SELECT
                check_name,
                check_status,
                details
            FROM (
                SELECT
                    'Active Keystore Status' AS check_name,
                    CASE
                        WHEN COUNT(*) > 0 AND COUNT(CASE WHEN status <> 'OPEN' THEN 1 END) = 0 THEN 'OK'
                        WHEN COUNT(*) = 0 THEN 'WARNING'
                        ELSE 'CRITICAL'
                    END AS check_status,
                    CASE
                        WHEN COUNT(*) = 0 THEN 'No keystore wallet found; TDE is not configured.'
                        WHEN COUNT(CASE WHEN status <> 'OPEN' THEN 1 END) = 0 THEN 'All keystore instances and PDBs are OPEN.'
                        ELSE 'One or more keystore instances/PDBs are NOT OPEN.'
                    END AS details
                FROM gv$encryption_wallet
                UNION ALL
                SELECT
                    'Master Key Backed Up' AS check_name,
                    CASE
                        WHEN COUNT(*) = 0 THEN 'INFO'
                        WHEN COUNT(CASE WHEN backed_up <> 'YES' THEN 1 END) = 0 THEN 'OK'
                        ELSE 'WARNING'
                    END AS check_status,
                    CASE
                        WHEN COUNT(*) = 0 THEN 'No master keys recorded.'
                        WHEN COUNT(CASE WHEN backed_up <> 'YES' THEN 1 END) = 0 THEN 'All master encryption keys (CDB & PDBs) are backed up in keystore.'
                        ELSE TO_CHAR(COUNT(CASE WHEN backed_up <> 'YES' THEN 1 END)) || ' key(s) are NOT backed up! Backup keystore immediately.'
                    END AS details
                FROM v$encryption_keys
                UNION ALL
                SELECT
                    'Keystore Full Backup' AS check_name,
                    CASE
                        WHEN COUNT(*) = 0 THEN 'INFO'
                        WHEN COUNT(CASE WHEN fully_backed_up = 'NO' THEN 1 END) = 0 THEN 'OK'
                        ELSE 'WARNING'
                    END AS check_status,
                    CASE
                        WHEN COUNT(*) = 0 THEN 'No keystore wallet found.'
                        WHEN COUNT(CASE WHEN fully_backed_up = 'NO' THEN 1 END) = 0 THEN 'Keystore has been fully backed up.'
                        ELSE 'Keystore has pending modifications not yet backed up.'
                    END AS details
                FROM gv$encryption_wallet
            )
            ORDER BY check_name
        """
        results: list[KeyHealthCheck] = []
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                for row in cur:
                    results.append(
                        KeyHealthCheck(
                            check_name=str(row[0]),
                            status=str(row[1]),
                            details=str(row[2]),
                        )
                    )
        except oracledb.DatabaseError as exc:
            logger.warning("Could not execute health checks: {}", exc)
        return results


def format_report_text(report: TdeKeyReport) -> str:
    """Format the TDE key report into human-readable plain text.

    Args:
        report: Structured TDE key report data.

    Returns:
        str: Formatted report text.
    """
    lines: list[str] = [
        "=" * 80,
        "Oracle Transparent Data Encryption (TDE) Key Information (CDB & PDBs)",
        f"Generated At : {report.generated_at}",
        "=" * 80,
        "",
        "--- 1. KEYSTORE / WALLET CONTEXT (GV$ENCRYPTION_WALLET) ---",
    ]

    if report.wallets:
        lines.append(f"{'Inst':<5} {'Con':<5} {'Container / PDB':<20} {'Type':<8} {'Status':<16} {'Wallet Type':<16} {'Backed Up':<10} {'Location'}")
        lines.append(f"{'-' * 5} {'-' * 5} {'-' * 20} {'-' * 8} {'-' * 16} {'-' * 16} {'-' * 10} {'-' * 20}")
        for w in report.wallets:
            con_str = str(w.con_id) if w.con_id is not None else "-"
            lines.append(f"{w.inst_id:<5} {con_str:<5} {w.container_name or '':<20} {w.wrl_type or '':<8} {w.status:<16} {w.wallet_type or '':<16} {w.fully_backed_up or '':<10} {w.wrl_parameter or ''}")
    else:
        lines.append("No keystore wallet records found.")
    lines.append("")

    # Active Master Key per PDB
    lines.append("--- 2. ACTIVE MASTER ENCRYPTION KEY(S) PER PDB ---")
    if report.active_keys:
        lines.append(f"{'Container / PDB':<18} {'Con':<5} {'Key ID Prefix':<32} {'Key Use':<22} {'Age Days':>9} {'Backed Up':<10} {'Tag'}")
        lines.append(f"{'-' * 18} {'-' * 5} {'-' * 32} {'-' * 22} {'-' * 9} {'-' * 10} {'-' * 10}")
        for k in report.active_keys:
            con_str = str(k.con_id) if k.con_id is not None else "-"
            key_id_disp = k.key_id[:30] + ".." if len(k.key_id) > 32 else k.key_id
            age_str = f"{k.age_days:.1f}" if k.age_days is not None else "-"
            lines.append(f"{k.pdb_name:<18} {con_str:<5} {key_id_disp:<32} {k.key_use or '':<22} {age_str:>9} {k.backed_up or 'NO':<10} {k.tag or '(none)'}")
    else:
        lines.append("No active master encryption keys found.")
    lines.append("")

    # Key History & Rekey Log per PDB
    lines.append("--- 3. KEY LIFECYCLE & REKEY HISTORY PER PDB (V$ENCRYPTION_KEYS) ---")
    if report.key_history:
        lines.append(f"{'Container / PDB':<18} {'Key ID Prefix':<32} {'Key Status':<18} {'Activated':<20} {'Backed Up':<10} {'Tag'}")
        lines.append(f"{'-' * 18} {'-' * 32} {'-' * 18} {'-' * 20} {'-' * 10} {'-' * 10}")
        for h in report.key_history:
            lines.append(f"{h.pdb_name:<18} {h.key_id_prefix:<32} {h.key_status:<18} {h.activated_time or 'PENDING':<20} {h.backed_up or 'NO':<10} {h.tag or ''}")
    else:
        lines.append("No key history records found.")
    lines.append("")

    # Tablespace Keys
    lines.append("--- 4. TABLESPACE ENCRYPTION KEYS & ALGORITHMS ---")
    if report.tablespace_keys:
        lines.append(f"{'Container / PDB':<18} {'Tablespace':<24} {'Algorithm':<14} {'Key Status':<12} {'Key Present'}")
        lines.append(f"{'-' * 18} {'-' * 24} {'-' * 14} {'-' * 12} {'-' * 12}")
        for tk in report.tablespace_keys:
            lines.append(f"{tk.pdb_name or 'CDB$ROOT':<18} {tk.tablespace_name:<24} {tk.encryption_alg:<14} {tk.key_status:<12} {tk.encrypted_key_state}")
    else:
        lines.append("No encrypted tablespaces found.")
    lines.append("")

    # Health Checks
    lines.append("--- 5. KEY SECURITY & BACKUP HEALTH CHECKS ---")
    if report.health_checks:
        lines.append(f"{'Check Name':<28} {'Status':<10} {'Details'}")
        lines.append(f"{'-' * 28} {'-' * 10} {'-' * 40}")
        for hc in report.health_checks:
            lines.append(f"{hc.check_name:<28} {hc.status:<10} {hc.details}")
    else:
        lines.append("No health check results available.")
    lines.append("")

    return "\n".join(lines)


def format_report_json(report: TdeKeyReport) -> str:
    """Format the TDE key report as JSON.

    Args:
        report: Structured TDE key report data.

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
        description="Audit and report Oracle Transparent Data Encryption (TDE) keys and keystores.",
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
        )
    except ValidationError as exc:
        logger.error("Invalid configuration: {}", exc)
        return 1

    driver = OracleDriver(config)
    reporter = TdeKeyReporter(driver)

    try:
        report = reporter.generate_report()
    except oracledb.DatabaseError as exc:
        logger.error("Failed to generate TDE key report: {}", exc)
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
