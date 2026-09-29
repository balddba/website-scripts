#!/usr/bin/env python3
# ===============================================================================
#
# Script Name: dataguard_stats.py
# Title: Basic Data Guard status and lag stats
# Tags: Python, Data Guard, Monitoring
# Purpose: Show database role, protection status, lag metrics, and recovery processes.
#
# Description:
#   Collects a concise Data Guard health snapshot from dynamic performance views,
#   including role/protection mode, V$DATAGUARD_STATS lag values, recovery
#   processes, and archive destination synchronization state.
#
# Parameters:
#   Command-line Oracle connection settings; use --help.
#
# Required Privileges:
#   - SELECT on V$DATABASE, V$DATAGUARD_STATS, GV$DATAGUARD_PROCESS, GV$MANAGED_STANDBY, GV$ARCHIVE_DEST_STATUS
#   - Or SELECT_CATALOG_ROLE
#
# Output Format:
#   - Plain-text sections by default; JSON with --json.
#
# Example Usage:
#   python dataguard_stats.py --host standby01 --service-name ORCL_DG --username system --password secret
#   python dataguard_stats.py --connect-string standby01:1521/ORCL_DG --username system --password secret --json
#
# Author: Aaron Myers <aaron@balddba.com>
#
# ===============================================================================
"""Show basic Oracle Data Guard status, lag metrics, and recovery processes."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import oracledb
import typer


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
        ctx = cmd.make_context("dataguard_stats", list(args) if args is not None else sys.argv[1:])
        ns = SimpleNamespace(**ctx.params)
        if hasattr(ns, "json_output"):
            ns.json = ns.json_output
        return ns


app = TyperApp(add_completion=False, help="Show basic Oracle Data Guard status and lag stats.")


@app.command()
def run(
    username: str = typer.Option(..., "--username", help="Oracle username."),
    password: str = typer.Option(..., "--password", help="Oracle password."),
    host: str = typer.Option("localhost", "--host", help="Database host name."),
    port: int = typer.Option(1521, "--port", help="Database listener port."),
    service_name: str | None = typer.Option(None, "--service-name", help="Oracle service name."),
    sid: str | None = typer.Option(None, "--sid", help="Oracle SID."),
    connect_string: str | None = typer.Option(None, "--connect-string", help="Full Oracle connect string. Overrides host/port/service-name."),
    sysdba: bool = typer.Option(False, "--sysdba", help="Connect as SYSDBA."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> int:
    """Run the Data Guard status and lag report command.

    Args:
        username (str): Oracle username.
        password (str): Oracle password.
        host (str): Database host name.
        port (int): Database listener port.
        service_name (str | None): Oracle service name.
        sid (str | None): Oracle SID.
        connect_string (str | None): Full Oracle connect string.
        sysdba (bool): Connect as SYSDBA.
        json_output (bool): Emit JSON instead of text.

    Returns:
        int: Process exit code.
    """
    args = SimpleNamespace(
        host=host,
        port=port,
        service_name=service_name,
        sid=sid,
        connect_string=connect_string,
        username=username,
        password=password,
        sysdba=sysdba,
        json=json_output,
    )
    with connect(args) as conn:
        report = collect_report(conn)
    if json_output:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)
    return 0


def parse_args(argv: Sequence[str]) -> SimpleNamespace:
    """Parse command-line arguments using Typer.

    Args:
        argv (Sequence[str]): Command-line arguments.

    Returns:
        SimpleNamespace: Parsed arguments.
    """
    args = list(argv[1:]) if len(argv) > 0 and argv[0].endswith(".py") else list(argv)
    return app.parse_args(args)


def build_dsn(args: Any) -> str:
    """Build an Oracle DSN from CLI arguments.

    Args:
        args (Any): Parsed CLI arguments.

    Returns:
        str: Formatted Oracle DSN.
    """
    if args.connect_string:
        return args.connect_string
    if args.service_name:
        return oracledb.makedsn(args.host, args.port, service_name=args.service_name)
    if args.sid:
        return oracledb.makedsn(args.host, args.port, sid=args.sid)
    return f"{args.host}:{args.port}"


@contextmanager
def connect(args: Any):
    """Open an Oracle connection.

    Args:
        args (Any): Parsed CLI arguments.

    Yields:
        oracledb.Connection: Open database connection.
    """
    mode = oracledb.SYSDBA if args.sysdba or args.username.upper() == "SYS" else 0
    with oracledb.connect(user=args.username, password=args.password, dsn=build_dsn(args), mode=mode) as conn:
        yield conn


def rows(conn: oracledb.Connection, sql: str) -> list[dict[str, Any]]:
    """Run a query and return dictionaries keyed by lowercase column name.

    Args:
        conn (oracledb.Connection): Active database connection.
        sql (str): SQL statement text.

    Returns:
        list[dict[str, Any]]: List of row mappings.
    """
    with conn.cursor() as cursor:
        cursor.execute(sql)
        columns = [col[0].lower() for col in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def collect_report(conn: oracledb.Connection) -> dict[str, list[dict[str, Any]]]:
    """Collect a basic Data Guard health snapshot.

    Args:
        conn (oracledb.Connection): Active database connection.

    Returns:
        dict[str, list[dict[str, Any]]]: Grouped report data.
    """
    return {
        "database": rows(
            conn,
            """
            SELECT name, db_unique_name, database_role, open_mode, protection_mode,
                   protection_level, switchover_status
            FROM v$database
            """,
        ),
        "lag_stats": rows(
            conn,
            """
            SELECT name, value, unit, time_computed, datum_time
            FROM v$dataguard_stats
            ORDER BY name
            """,
        ),
        "dataguard_processes": rows(
            conn,
            """
            SELECT inst_id, name AS process_name, pid, role, action, client_pid,
                   thread#, sequence#, block#
            FROM gv$dataguard_process
            ORDER BY inst_id, name, thread#
            """,
        ),
        "managed_standby": rows(
            conn,
            """
            SELECT inst_id, process AS process_name, pid, status, client_process,
                   thread#, sequence#, block#
            FROM gv$managed_standby
            ORDER BY inst_id, process, thread#
            """,
        ),
        "destinations": rows(
            conn,
            """
            SELECT inst_id, dest_id, dest_name, type AS dest_type, status, synchronized,
                   gap_status, archived_seq#, applied_seq#, error
            FROM gv$archive_dest_status
            WHERE status != 'INACTIVE'
            ORDER BY inst_id, dest_id
            """,
        ),
    }


def print_section(title: str, data: list[dict[str, Any]]) -> None:
    """Print a simple aligned table.

    Args:
        title (str): Section header title.
        data (list[dict[str, Any]]): List of row dictionaries.
    """
    print(f"\n=== {title} ===")
    if not data:
        print("No rows returned.")
        return
    columns = list(data[0])
    widths = {col: max(len(col), *(len(str(row.get(col, ""))) for row in data)) for col in columns}
    print("  ".join(col.upper().ljust(widths[col]) for col in columns))
    print("  ".join("-" * widths[col] for col in columns))
    for row in data:
        print("  ".join(str(row.get(col, "") or "").ljust(widths[col]) for col in columns))


def print_report(report: dict[str, list[dict[str, Any]]]) -> None:
    """Print the report in text format.

    Args:
        report (dict[str, list[dict[str, Any]]]): Compiled report data dictionary.
    """
    print("Basic Data Guard Status")
    for title, key in (
        ("Database", "database"),
        ("Lag Stats", "lag_stats"),
        ("Data Guard Processes", "dataguard_processes"),
        ("Managed Standby", "managed_standby"),
        ("Archive Destinations", "destinations"),
    ):
        print_section(title, report[key])


def main(argv: Sequence[str] | None = None) -> int:
    """Run the script.

    Args:
        argv (Sequence[str] | None): Optional command-line arguments.

    Returns:
        int: Process exit code.
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
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    app()
