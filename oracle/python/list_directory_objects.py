#!/usr/bin/env python3
# ===============================================================================
#
# Script Name: list_directory_objects.py
# Title: List Oracle directory objects
# Tags: Python, Directories, Security
# Purpose: List Oracle directory objects and their granted privileges.
#
# Description:
#   Reports database directory names, filesystem paths, owners, and grants,
#   optionally filtering the results by directory name.
#
# Parameters:
#   Command-line Oracle connection settings and directory filter; use --help.
#
# Required Privileges:
#   - Read access to the Oracle catalog views queried by the script
#
# Output Format:
#   - Directory report written to standard output or the requested output file
#
# Example Usage:
#   python list_directory_objects.py --help
#
# Author: Aaron Myers <aaron@balddba.com>
#
# ===============================================================================
"""List and inspect Oracle database directory objects and permissions."""

from __future__ import annotations

import sys
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import oracledb
import typer
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
        directory_filter: Optional filter for directory name.
    """

    model_config = {"extra": "forbid"}

    hostname: str = Field(default="localhost", description="Database hostname")
    port: int = Field(default=1521, description="Database port")
    service_name: str | None = Field(default=None, description="Oracle service name")
    sid: str | None = Field(default=None, description="Oracle SID")
    username: str = Field(..., description="Database username")
    password: SecretStr = Field(..., description="Database password")
    is_sysdba: bool = Field(default=False, description="Connect with SYSDBA mode")
    directory_filter: str | None = Field(default=None, description="Directory name filter")


class DirectoryPrivilege(BaseModel):
    """Privilege grant on an Oracle directory object.

    Attributes:
        grantee: User or role granted the privilege.
        privilege: Granted privilege (e.g. READ, WRITE, EXECUTE).
        grantable: Whether grantee can grant privilege to others (YES/NO).
    """

    model_config = {"extra": "forbid"}

    grantee: str
    privilege: str
    grantable: str


class DirectoryObject(BaseModel):
    """Representation of an Oracle database directory object.

    Attributes:
        owner: Directory owner (typically SYS).
        directory_name: Database directory alias name.
        directory_path: Operating system filesystem path.
        privileges: List of privileges granted on this directory.
    """

    model_config = {"extra": "forbid"}

    owner: str
    directory_name: str
    directory_path: str
    privileges: list[DirectoryPrivilege] = Field(default_factory=list)


class DirectoryReportSummary(BaseModel):
    """Summary of database directory objects.

    Attributes:
        total_directories: Count of directory objects found.
        directories: List of detailed directory objects.
    """

    model_config = {"extra": "forbid"}

    total_directories: int
    directories: list[DirectoryObject]


class OracleDriver:
    """Manages connections and session lifecycle for Oracle database."""

    def __init__(self, config: OracleConnectionConfig) -> None:
        """Initialize the Oracle driver with connection settings.

        Args:
            config (OracleConnectionConfig): Oracle connection settings and credentials.
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


class DirectoryObjectsLister:
    """Service to list Oracle directory objects and associated privileges."""

    def __init__(
        self,
        driver: OracleDriver,
        directory_filter: str | None = None,
        include_privileges: bool = True,
    ) -> None:
        """Initialize the directory objects lister service.

        Args:
            driver (OracleDriver): Oracle database session driver.
            directory_filter (str | None): Optional directory name pattern to filter by.
            include_privileges (bool): Whether to query and attach privilege grants.
        """
        self._driver = driver
        self._directory_filter = directory_filter.upper() if directory_filter else None
        self._include_privileges = include_privileges

    def list_directories(self) -> DirectoryReportSummary:
        """Query database catalog views and compile the directory summary.

        Returns:
            DirectoryReportSummary: Summary containing all discovered directory objects.
        """
        with self._driver.session() as conn:
            directories = self._fetch_directories(conn)
            if self._include_privileges and directories:
                privileges_map = self._fetch_privileges(conn)
                for directory in directories:
                    directory.privileges = privileges_map.get(directory.directory_name, [])

        return DirectoryReportSummary(
            total_directories=len(directories),
            directories=directories,
        )

    def _fetch_directories(self, conn: oracledb.Connection) -> list[DirectoryObject]:
        """Fetch directory definitions from DBA_DIRECTORIES or ALL_DIRECTORIES.

        Args:
            conn (oracledb.Connection): Active Oracle connection.

        Returns:
            list[DirectoryObject]: List of discovered directory objects.
        """
        sql_dba = """
            SELECT owner, directory_name, directory_path
            FROM dba_directories
            WHERE (:dir_filter IS NULL OR UPPER(directory_name) LIKE '%' || :dir_filter || '%')
            ORDER BY directory_name
        """
        sql_all = """
            SELECT owner, directory_name, directory_path
            FROM all_directories
            WHERE (:dir_filter IS NULL OR UPPER(directory_name) LIKE '%' || :dir_filter || '%')
            ORDER BY directory_name
        """
        bind_params: dict[str, Any] = {"dir_filter": self._directory_filter}

        rows = self._query_with_fallback(conn, sql_dba, sql_all, bind_params)
        results: list[DirectoryObject] = []
        for row in rows:
            results.append(
                DirectoryObject(
                    owner=str(row[0]),
                    directory_name=str(row[1]),
                    directory_path=str(row[2]),
                )
            )
        return results

    def _fetch_privileges(self, conn: oracledb.Connection) -> dict[str, list[DirectoryPrivilege]]:
        """Fetch privilege grants on directories from DBA_TAB_PRIVS or ALL_TAB_PRIVS.

        Args:
            conn (oracledb.Connection): Active Oracle connection.

        Returns:
            dict[str, list[DirectoryPrivilege]]: Privilege grants indexed by directory name.
        """
        sql_dba = """
            SELECT table_name, grantee, privilege, grantable
            FROM dba_tab_privs
            WHERE type = 'DIRECTORY'
              AND (:dir_filter IS NULL OR UPPER(table_name) LIKE '%' || :dir_filter || '%')
            ORDER BY table_name, grantee, privilege
        """
        sql_all = """
            SELECT table_name, grantee, privilege, grantable
            FROM all_tab_privs
            WHERE type = 'DIRECTORY'
              AND (:dir_filter IS NULL OR UPPER(table_name) LIKE '%' || :dir_filter || '%')
            ORDER BY table_name, grantee, privilege
        """
        bind_params: dict[str, Any] = {"dir_filter": self._directory_filter}

        privs_map: dict[str, list[DirectoryPrivilege]] = {}
        try:
            rows = self._query_with_fallback(conn, sql_dba, sql_all, bind_params)
            for row in rows:
                dir_name = str(row[0])
                grantee = str(row[1])
                privilege = str(row[2])
                grantable = str(row[3])

                if dir_name not in privs_map:
                    privs_map[dir_name] = []
                privs_map[dir_name].append(
                    DirectoryPrivilege(
                        grantee=grantee,
                        privilege=privilege,
                        grantable=grantable,
                    )
                )
        except oracledb.DatabaseError as exc:
            logger.warning(
                "Could not query directory privileges, skipping privilege details: {}",
                exc,
            )

        return privs_map

    def _query_with_fallback(
        self,
        conn: oracledb.Connection,
        primary_sql: str,
        fallback_sql: str,
        params: dict[str, Any],
    ) -> list[tuple[Any, ...]]:
        """Execute a catalog query with fallback to ALL_ views if DBA_ views are inaccessible.

        Args:
            conn (oracledb.Connection): Active Oracle connection.
            primary_sql (str): Primary SQL referencing DBA_ view.
            fallback_sql (str): Fallback SQL referencing ALL_ view.
            params (dict[str, Any]): Bind parameters dictionary.

        Returns:
            list[tuple[Any, ...]]: Result rows.

        Raises:
            oracledb.DatabaseError: If both queries fail.
        """
        with conn.cursor() as cursor:
            try:
                cursor.execute(primary_sql, params)
                return cursor.fetchall()
            except oracledb.DatabaseError as exc:
                err_obj = exc.args[0] if exc.args else None
                err_code = getattr(err_obj, "code", 0)
                # ORA-00942: table or view does not exist
                if err_code == 942:
                    logger.warning("DBA view inaccessible (ORA-00942), falling back to ALL_ catalog view")
                    try:
                        cursor.execute(fallback_sql, params)
                        return cursor.fetchall()
                    except oracledb.DatabaseError as fallback_exc:
                        logger.error("Fallback query failed: {}", fallback_exc)
                        raise
                logger.error("Catalog query failed: {}", exc)
                raise


def format_directories_text(report: DirectoryReportSummary, show_privileges: bool = True) -> str:
    """Format directory report summary as a human-readable text table.

    Args:
        report (DirectoryReportSummary): Compiled directory report summary.
        show_privileges (bool): Whether to render privilege details.

    Returns:
        str: Formatted report text.
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "=" * 80,
        " ORACLE DIRECTORY OBJECTS REPORT",
        f" Generated: {now_str}",
        "=" * 80,
        f" Total Directories: {report.total_directories}",
        "",
    ]

    if report.total_directories == 0:
        lines.append("No directory objects found in the database.")
        lines.append("=" * 80)
        return "\n".join(lines)

    lines.append(f"{'DIRECTORY NAME':<30} {'OWNER':<10} {'PATH'}")
    lines.append("-" * 80)

    for dir_obj in report.directories:
        lines.append(f"{dir_obj.directory_name:<30} {dir_obj.owner:<10} {dir_obj.directory_path}")
        if show_privileges and dir_obj.privileges:
            for priv in dir_obj.privileges:
                grantable_str = " (ADMIN)" if priv.grantable == "YES" else ""
                lines.append(f"    Grantee: {priv.grantee:<20} Privilege: {priv.privilege}{grantable_str}")

    lines.append("=" * 80)
    return "\n".join(lines)


class TyperApp(typer.Typer):
    """Typer application with parse_args support for programmatic parsing."""

    def parse_args(self, args: Sequence[str] | None = None) -> SimpleNamespace:
        """Parse arguments into a namespace for programmatic use.

        Args:
            args (Sequence[str] | None): Argument list to parse.

        Returns:
            SimpleNamespace: Parsed arguments as a namespace.
        """
        cmd = typer.main.get_command(self)
        ctx = cmd.make_context("list_directory_objects", list(args) if args is not None else sys.argv[1:])
        ns = SimpleNamespace(**ctx.params)
        if hasattr(ns, "directory_filter") and not hasattr(ns, "filter"):
            ns.filter = ns.directory_filter
        if hasattr(ns, "json_output") and not hasattr(ns, "json"):
            ns.json = ns.json_output
        return ns


app = TyperApp(add_completion=False, help="List and inspect directory objects in an Oracle database.")


@app.command()
def run(
    host: str = typer.Option("localhost", "--host", envvar="ORACLE_HOST", help="Oracle database host"),
    port: int = typer.Option(1521, "--port", envvar="ORACLE_PORT", help="Oracle database port"),
    service_name: str | None = typer.Option(None, "--service-name", envvar="ORACLE_SERVICE_NAME", help="Oracle service name"),
    sid: str | None = typer.Option(None, "--sid", envvar="ORACLE_SID", help="Oracle SID"),
    user: str | None = typer.Option(None, "--user", envvar="ORACLE_USER", help="Database username"),
    password: str | None = typer.Option(None, "--password", envvar="ORACLE_PASSWORD", help="Database password"),
    sysdba: bool = typer.Option(False, "--sysdba", help="Connect with SYSDBA privilege"),
    directory_filter: str | None = typer.Option(None, "--filter", envvar="ORACLE_DIRECTORY_FILTER", help="Filter directory name"),
    no_privileges: bool = typer.Option(False, "--no-privileges", help="Omit privilege inspection for faster queries"),
    json_output: bool = typer.Option(False, "--json", help="Output report in JSON format"),
    output: str | None = typer.Option(None, "--output", help="File path to save the output report"),
) -> int:
    """List and inspect directory objects in an Oracle database.

    Args:
        host (str): Database host.
        port (int): Database port.
        service_name (str | None): Oracle service name.
        sid (str | None): Oracle SID.
        user (str | None): Database username.
        password (str | None): Database password.
        sysdba (bool): Connect with SYSDBA privilege.
        directory_filter (str | None): Directory name filter.
        no_privileges (bool): Omit privileges.
        json_output (bool): Output in JSON format.
        output (str | None): Output file path.

    Returns:
        int: Exit status code.
    """
    if not user:
        logger.error("Database username must be specified via --user or ORACLE_USER")
        return 1
    if not password:
        logger.error("Database password must be specified via --password or ORACLE_PASSWORD")
        return 1
    if not service_name and not sid:
        logger.error("Either --service-name or --sid must be specified (or via environment variables)")
        return 1

    try:
        config = OracleConnectionConfig(
            hostname=host,
            port=port,
            service_name=service_name,
            sid=sid,
            username=user,
            password=SecretStr(password),
            is_sysdba=sysdba,
            directory_filter=directory_filter,
        )
    except ValidationError as exc:
        logger.error("Configuration validation failed: {}", exc)
        return 1

    driver = OracleDriver(config)
    lister = DirectoryObjectsLister(
        driver,
        directory_filter=config.directory_filter,
        include_privileges=not no_privileges,
    )

    try:
        report = lister.list_directories()
    except oracledb.DatabaseError as exc:
        logger.error("Database error while querying directory objects: {}", exc)
        return 1

    if json_output:
        output_text = report.model_dump_json(indent=2)
    else:
        output_text = format_directories_text(report, show_privileges=not no_privileges)

    if output:
        try:
            with open(output, "w", encoding="utf-8") as f:
                f.write(output_text)
            logger.info("Directory report saved to {}", output)
        except OSError as exc:
            logger.error("Failed to write report to {}: {}", output, exc)
            return 1
    else:
        sys.stdout.write(output_text + "\n")

    return 0


def build_parser() -> TyperApp:
    """Build and return the CLI argument parser.

    Returns:
        TyperApp: Configured parser.
    """
    return app


def main(argv: Sequence[str] | None = None) -> int:
    """CLI execution entrypoint.

    Args:
        argv (Sequence[str] | None): Optional command-line arguments.

    Returns:
        int: Exit status code.
    """
    try:
        args = list(argv) if argv is not None else None
        ret = app(args=args, standalone_mode=False)
        return 0 if ret is None else int(ret)
    except typer.Exit as exc:
        return exc.exit_code
    except Exception as exc:
        logger.error("{}", exc)
        return 1


if __name__ == "__main__":
    app()
