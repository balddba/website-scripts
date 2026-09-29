#!/usr/bin/env python3
# ===============================================================================
#
# Script Name: report_invalid_objects.py
# Title: Report invalid Oracle objects
# Tags: Python, Invalid Objects, Administration
# Purpose: Report invalid Oracle objects and their compilation errors.
#
# Description:
#   Lists invalid objects, summarizes them by type and owner, and includes
#   available compiler diagnostics to support remediation.
#
# Parameters:
#   Command-line Oracle connection settings and owner filter; use --help.
#
# Required Privileges:
#   - Read access to the Oracle catalog views queried by the script
#
# Output Format:
#   - Invalid-object report written to standard output or the requested file
#
# Example Usage:
#   python report_invalid_objects.py --help
#
# Author: Aaron Myers <aaron@balddba.com>
#
# ===============================================================================
"""Report invalid database objects and their compilation errors in Oracle database."""

from __future__ import annotations

import sys
from collections import Counter
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


class ObjectCompileError(BaseModel):
    """Compilation error detail for an invalid Oracle object.

    Attributes:
        line: Source code line number.
        position: Source code character position.
        text: Error message text.
    """

    model_config = {"extra": "forbid"}

    line: int
    position: int
    text: str


class InvalidObject(BaseModel):
    """Representation of an invalid Oracle database object.

    Attributes:
        owner: Schema owner name.
        object_name: Name of the invalid object.
        object_type: Type of object (e.g. PACKAGE BODY, VIEW, TRIGGER).
        status: Object status (typically INVALID).
        created: Timestamp when object was created.
        last_ddl_time: Timestamp when object was last modified.
        errors: List of compilation errors from catalog views.
    """

    model_config = {"extra": "forbid"}

    owner: str
    object_name: str
    object_type: str
    status: str
    created: datetime | None = None
    last_ddl_time: datetime | None = None
    errors: list[ObjectCompileError] = Field(default_factory=list)


class ReportSummary(BaseModel):
    """Summary of the invalid objects report.

    Attributes:
        total_invalid_objects: Total count of invalid objects found.
        objects_by_type: Count of invalid objects grouped by object type.
        objects_by_owner: Count of invalid objects grouped by schema owner.
        items: Detailed list of invalid objects.
    """

    model_config = {"extra": "forbid"}

    total_invalid_objects: int
    objects_by_type: dict[str, int]
    objects_by_owner: dict[str, int]
    items: list[InvalidObject]


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


class InvalidObjectsReporter:
    """Service to discover invalid database objects and their compile errors."""

    def __init__(self, driver: OracleDriver, owner_filter: str | None = None) -> None:
        """Initialize the reporter service.

        Args:
            driver (OracleDriver): Oracle database session driver.
            owner_filter (str | None): Optional schema owner to filter objects by.
        """
        self._driver = driver
        self._owner_filter = owner_filter.upper() if owner_filter else None

    def generate_report(self) -> ReportSummary:
        """Execute queries and compile the full invalid objects report.

        Returns:
            ReportSummary: Complete summary report with error details.
        """
        with self._driver.session() as conn:
            invalid_objects = self._fetch_invalid_objects(conn)
            errors_map = self._fetch_compile_errors(conn)

        for obj in invalid_objects:
            key = (obj.owner, obj.object_type, obj.object_name)
            if key in errors_map:
                obj.errors = errors_map[key]

        type_counts = Counter(obj.object_type for obj in invalid_objects)
        owner_counts = Counter(obj.owner for obj in invalid_objects)

        return ReportSummary(
            total_invalid_objects=len(invalid_objects),
            objects_by_type=dict(type_counts),
            objects_by_owner=dict(owner_counts),
            items=invalid_objects,
        )

    def _fetch_invalid_objects(self, conn: oracledb.Connection) -> list[InvalidObject]:
        """Fetch invalid objects from DBA_OBJECTS or ALL_OBJECTS.

        Args:
            conn (oracledb.Connection): Active Oracle connection.

        Returns:
            list[InvalidObject]: List of invalid objects found.
        """
        sql_dba = """
            SELECT owner, object_name, object_type, status, created, last_ddl_time
            FROM dba_objects
            WHERE status = 'INVALID'
              AND (:owner IS NULL OR owner = :owner)
            ORDER BY owner, object_type, object_name
        """
        sql_all = """
            SELECT owner, object_name, object_type, status, created, last_ddl_time
            FROM all_objects
            WHERE status = 'INVALID'
              AND (:owner IS NULL OR owner = :owner)
            ORDER BY owner, object_type, object_name
        """
        bind_params: dict[str, Any] = {"owner": self._owner_filter}

        rows = self._query_with_fallback(conn, sql_dba, sql_all, bind_params)
        results: list[InvalidObject] = []
        for row in rows:
            results.append(
                InvalidObject(
                    owner=str(row[0]),
                    object_name=str(row[1]),
                    object_type=str(row[2]),
                    status=str(row[3]),
                    created=row[4] if isinstance(row[4], datetime) else None,
                    last_ddl_time=row[5] if isinstance(row[5], datetime) else None,
                )
            )
        return results

    def _fetch_compile_errors(self, conn: oracledb.Connection) -> dict[tuple[str, str, str], list[ObjectCompileError]]:
        """Fetch compilation errors from DBA_ERRORS or ALL_ERRORS.

        Args:
            conn (oracledb.Connection): Active Oracle connection.

        Returns:
            dict[tuple[str, str, str], list[ObjectCompileError]]: Errors indexed by (owner, type, name).
        """
        sql_dba = """
            SELECT owner, name, type, line, position, text
            FROM dba_errors
            WHERE (:owner IS NULL OR owner = :owner)
            ORDER BY owner, name, type, sequence
        """
        sql_all = """
            SELECT owner, name, type, line, position, text
            FROM all_errors
            WHERE (:owner IS NULL OR owner = :owner)
            ORDER BY owner, name, type, sequence
        """
        bind_params: dict[str, Any] = {"owner": self._owner_filter}

        rows = self._query_with_fallback(conn, sql_dba, sql_all, bind_params)
        errors_map: dict[tuple[str, str, str], list[ObjectCompileError]] = {}
        for row in rows:
            owner = str(row[0])
            name = str(row[1])
            obj_type = str(row[2])
            line = int(row[3]) if row[3] is not None else 0
            position = int(row[4]) if row[4] is not None else 0
            text = str(row[5]).strip() if row[5] is not None else ""

            key = (owner, obj_type, name)
            if key not in errors_map:
                errors_map[key] = []
            errors_map[key].append(ObjectCompileError(line=line, position=position, text=text))

        return errors_map

    def _query_with_fallback(
        self,
        conn: oracledb.Connection,
        primary_sql: str,
        fallback_sql: str,
        params: dict[str, Any],
    ) -> list[tuple[Any, ...]]:
        """Execute a query with fallback to ALL_ views if DBA_ views are inaccessible.

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


def format_report_text(report: ReportSummary) -> str:
    """Format report summary as a human-readable text table.

    Args:
        report (ReportSummary): Compiled report summary.

    Returns:
        str: Formatted report text.
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "=" * 80,
        " ORACLE INVALID OBJECTS REPORT",
        f" Generated: {now_str}",
        "=" * 80,
        f" Total Invalid Objects: {report.total_invalid_objects}",
        "",
    ]

    if report.total_invalid_objects == 0:
        lines.append("No invalid objects found in the database.")
        lines.append("=" * 80)
        return "\n".join(lines)

    lines.append("--- Breakdown by Object Type ---")
    for obj_type, count in sorted(report.objects_by_type.items()):
        lines.append(f"  {obj_type:<25}: {count}")
    lines.append("")

    lines.append("--- Breakdown by Owner ---")
    for owner, count in sorted(report.objects_by_owner.items()):
        lines.append(f"  {owner:<25}: {count}")
    lines.append("")

    lines.append("--- Invalid Objects Details ---")
    lines.append(f"{'OWNER':<15} {'TYPE':<20} {'OBJECT NAME':<30} {'ERRORS'}")
    lines.append("-" * 80)

    for item in report.items:
        err_count_str = f"{len(item.errors)} error(s)" if item.errors else "None"
        lines.append(f"{item.owner:<15} {item.object_type:<20} {item.object_name:<30} {err_count_str}")
        for err in item.errors:
            lines.append(f"    Line {err.line}, Col {err.position}: {err.text}")

    lines.append("=" * 80)
    return "\n".join(lines)


class TyperApp(typer.Typer):
    """Typer application with parse_args support for programmatic parsing."""

    def parse_args(self, args: Sequence[str] | None = None) -> SimpleNamespace:
        """Parse arguments into a namespace for programmatic use.

        Args:
            args (Sequence[str] | None): Arguments to parse.

        Returns:
            SimpleNamespace: Namespace of parsed arguments.
        """
        cmd = typer.main.get_command(self)
        ctx = cmd.make_context("report_invalid_objects", list(args) if args is not None else sys.argv[1:])
        ns = SimpleNamespace(**ctx.params)
        if hasattr(ns, "json_output"):
            ns.json = ns.json_output
        elif hasattr(ns, "json"):
            ns.json_output = ns.json
        return ns


app = TyperApp(add_completion=False, help="Inspect and report invalid objects in an Oracle database.")


@app.command()
def run(
    host: str = typer.Option(
        "localhost",
        "--host",
        envvar="ORACLE_HOST",
        help="Oracle database host (default: ORACLE_HOST or localhost)",
    ),
    port: int = typer.Option(
        1521,
        "--port",
        envvar="ORACLE_PORT",
        help="Oracle database port (default: ORACLE_PORT or 1521)",
    ),
    service_name: str | None = typer.Option(
        None,
        "--service-name",
        envvar="ORACLE_SERVICE_NAME",
        help="Oracle service name (default: ORACLE_SERVICE_NAME)",
    ),
    sid: str | None = typer.Option(
        None,
        "--sid",
        envvar="ORACLE_SID",
        help="Oracle SID (default: ORACLE_SID)",
    ),
    user: str | None = typer.Option(
        None,
        "--user",
        envvar="ORACLE_USER",
        help="Database username (default: ORACLE_USER)",
    ),
    password: str | None = typer.Option(
        None,
        "--password",
        envvar="ORACLE_PASSWORD",
        help="Database password (default: ORACLE_PASSWORD)",
    ),
    sysdba: bool = typer.Option(
        False,
        "--sysdba",
        help="Connect with SYSDBA privilege",
    ),
    owner: str | None = typer.Option(
        None,
        "--owner",
        envvar="ORACLE_OWNER",
        help="Filter by schema owner (default: all schemas accessible)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output report in JSON format",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        help="File path to save the output report",
    ),
) -> int:
    """Execute invalid objects reporting.

    Args:
        host (str): Database hostname.
        port (int): Database port.
        service_name (str | None): Oracle service name.
        sid (str | None): Oracle SID.
        user (str | None): Database username.
        password (str | None): Database password.
        sysdba (bool): Whether to connect with SYSDBA privilege.
        owner (str | None): Optional schema owner filter.
        json_output (bool): Output report in JSON format.
        output (str | None): File path to save output report.

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
            owner=owner,
        )
    except ValidationError as exc:
        logger.error("Configuration validation failed: {}", exc)
        return 1

    driver = OracleDriver(config)
    reporter = InvalidObjectsReporter(driver, owner_filter=config.owner)

    try:
        report = reporter.generate_report()
    except oracledb.DatabaseError as exc:
        logger.error("Database error while generating report: {}", exc)
        return 1

    if json_output:
        output_text = report.model_dump_json(indent=2)
    else:
        output_text = format_report_text(report)

    if output:
        try:
            with open(output, "w", encoding="utf-8") as f:
                f.write(output_text)
            logger.info("Report saved to {}", output)
        except OSError as exc:
            logger.error("Failed to write report to {}: {}", output, exc)
            return 1
    else:
        # Output directly to stdout for CLI consumption
        sys.stdout.write(output_text + "\n")

    return 0 if report.total_invalid_objects == 0 else 2


def build_parser() -> TyperApp:
    """Construct CLI argument parser for the report script.

    Returns:
        TyperApp: Configured Typer application.
    """
    return app


def main(argv: Sequence[str] | None = None) -> int:
    """CLI execution entrypoint.

    Args:
        argv (Sequence[str] | None): Command-line arguments.

    Returns:
        int: Exit status code.
    """
    try:
        if argv is not None:
            args = list(argv[1:]) if len(argv) > 0 and argv[0].endswith(".py") else list(argv)
        else:
            args = None
        ret = app(args=args, standalone_mode=False)
        return 0 if ret is None else int(ret)
    except typer.Exit as exc:
        return exc.exit_code
    except (typer.BadParameter, typer.exceptions.TyperException) as exc:
        sys.exit(getattr(exc, "exit_code", 2))
    except Exception as exc:
        logger.error("{}", exc)
        return 1


if __name__ == "__main__":
    app()
