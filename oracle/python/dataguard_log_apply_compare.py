#!/usr/bin/env python3
#===============================================================================
#
# Script Name: dataguard_log_apply_compare.py
# Title: Data Guard primary versus standby applied logs
# Tags: Python, Data Guard, Redo Apply
# Purpose: Compare archived redo on the primary with applied redo on the standby.
#
# Description:
#   Shows the highest archived and applied redo sequence per thread from the
#   connected database's Data Guard catalog views, highlighting apply lag by
#   sequence number and last apply time.
#
# Parameters:
#   Command-line Oracle connection settings; use --help.
#
# Required Privileges:
#   - SELECT on V$DATABASE, GV$ARCHIVE_DEST_STATUS, V$ARCHIVED_LOG
#   - Or SELECT_CATALOG_ROLE
#
# Output Format:
#   - Plain-text sections by default; JSON with --json.
#
# Example Usage:
#   python dataguard_log_apply_compare.py --connect-string primary01:1521/ORCL --username system --password secret
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
"""Compare Oracle Data Guard archived and applied redo sequences."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from contextlib import contextmanager
from typing import Any

import oracledb


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Compare archived and applied Data Guard redo logs.")
    parser.add_argument("--host", default="localhost", help="Database host name.")
    parser.add_argument("--port", type=int, default=1521, help="Database listener port.")
    parser.add_argument("--service-name", help="Oracle service name.")
    parser.add_argument("--sid", help="Oracle SID.")
    parser.add_argument("--connect-string", help="Full Oracle connect string. Overrides host/port/service-name.")
    parser.add_argument("--username", required=True, help="Oracle username.")
    parser.add_argument("--password", required=True, help="Oracle password.")
    parser.add_argument("--sysdba", action="store_true", help="Connect as SYSDBA.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser.parse_args(argv[1:])


def build_dsn(args: argparse.Namespace) -> str:
    """Build an Oracle DSN from CLI arguments."""
    if args.connect_string:
        return args.connect_string
    if args.service_name:
        return oracledb.makedsn(args.host, args.port, service_name=args.service_name)
    if args.sid:
        return oracledb.makedsn(args.host, args.port, sid=args.sid)
    return f"{args.host}:{args.port}"


@contextmanager
def connect(args: argparse.Namespace):
    """Open an Oracle connection."""
    mode = oracledb.SYSDBA if args.sysdba or args.username.upper() == "SYS" else 0
    with oracledb.connect(user=args.username, password=args.password, dsn=build_dsn(args), mode=mode) as conn:
        yield conn


def rows(conn: oracledb.Connection, sql: str) -> list[dict[str, Any]]:
    """Run a query and return dictionaries keyed by lowercase column name."""
    with conn.cursor() as cursor:
        cursor.execute(sql)
        columns = [col[0].lower() for col in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def collect_report(conn: oracledb.Connection) -> dict[str, list[dict[str, Any]]]:
    """Collect archived and applied redo comparison data."""
    return {
        "database": rows(
            conn,
            """
            SELECT name, db_unique_name, database_role, open_mode, protection_mode, switchover_status
            FROM v$database
            """,
        ),
        "destination_sequences": rows(
            conn,
            """
            SELECT inst_id, dest_id, dest_name, type AS dest_type, status, synchronized, gap_status,
                   archived_thread#, archived_seq#, applied_thread#, applied_seq#,
                   CASE
                       WHEN archived_seq# IS NULL OR applied_seq# IS NULL THEN NULL
                       ELSE archived_seq# - applied_seq#
                   END AS sequence_diff,
                   error
            FROM gv$archive_dest_status
            WHERE status != 'INACTIVE'
            ORDER BY inst_id, dest_id
            """,
        ),
        "local_thread_sequences": rows(
            conn,
            """
            SELECT thread#,
                   MAX(sequence#) AS highest_known_sequence,
                   MAX(CASE WHEN archived = 'YES' THEN sequence# END) AS highest_archived_sequence,
                   MAX(CASE WHEN applied = 'YES' THEN sequence# END) AS highest_applied_sequence,
                   MAX(sequence#) - NVL(MAX(CASE WHEN applied = 'YES' THEN sequence# END), 0) AS unapplied_sequences,
                   TO_CHAR(MAX(CASE WHEN applied = 'YES' THEN next_time END), 'YYYY-MM-DD HH24:MI:SS') AS last_applied_time
            FROM v$archived_log
            WHERE resetlogs_change# = (SELECT resetlogs_change# FROM v$database)
            GROUP BY thread#
            ORDER BY thread#
            """,
        ),
        "recent_unapplied": rows(
            conn,
            """
            SELECT *
            FROM (
                SELECT thread#, sequence#, first_time, next_time, name
                FROM v$archived_log
                WHERE resetlogs_change# = (SELECT resetlogs_change# FROM v$database)
                  AND archived = 'YES'
                  AND NVL(applied, 'NO') != 'YES'
                ORDER BY thread#, sequence#
            )
            WHERE ROWNUM <= 50
            """,
        ),
    }


def print_section(title: str, data: list[dict[str, Any]]) -> None:
    """Print a simple aligned table."""
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
    """Print the report in text format."""
    print("Data Guard Primary vs Standby Applied Logs")
    for title, key in (
        ("Database", "database"),
        ("Destination Sequences", "destination_sequences"),
        ("Local Thread Sequences", "local_thread_sequences"),
        ("Recent Unapplied Logs", "recent_unapplied"),
    ):
        print_section(title, report[key])


def main(argv: Sequence[str]) -> int:
    """Run the script."""
    args = parse_args(argv)
    with connect(args) as conn:
        report = collect_report(conn)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
