#!/usr/bin/env python3
# ===============================================================================
#
# Script Name: memory_tree.py
# Title: Oracle SGA and PGA memory tree
# Tags: Python, Memory, SGA, PGA, Performance
# Purpose: Display Oracle SGA and PGA memory usage as hierarchical terminal trees.
#
# Description:
#   Connects to an Oracle instance and renders SGA pools and allocations from
#   V$SGA and V$SGASTAT, plus PGA aggregate statistics from V$PGASTAT. Child
#   nodes show their size and percentage of the parent memory area.
#
# Parameters:
#   Command-line Oracle connection settings and minimum allocation size; use --help.
#
# Required Privileges:
#   - SELECT on V$SGA
#   - SELECT on V$SGASTAT
#   - SELECT on V$PGASTAT
#   - Or SELECT_CATALOG_ROLE
#
# Output Format:
#   - Rich terminal trees for SGA and PGA memory usage
#
# Example Usage:
#   python memory_tree.py --service-name ORCLPDB1 --user system --password secret
#   python memory_tree.py --service-name ORCLPDB1 --user system --password secret --min-mb 10
#   ORACLE_USER=system ORACLE_PASSWORD=secret python memory_tree.py --service-name ORCLPDB1
#
# Author: Aaron Myers <aaron@balddba.com>
#
# ===============================================================================
"""Display Oracle SGA and PGA memory usage as terminal trees."""

from __future__ import annotations

import sys
from collections import defaultdict
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace

import oracledb
import typer
from loguru import logger
from pydantic import BaseModel, Field, SecretStr, ValidationError
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree


class OracleConnectionConfig(BaseModel):
    """Validated Oracle connection settings."""

    model_config = {"extra": "forbid"}

    hostname: str = Field(default="localhost")
    port: int = Field(default=1521, ge=1, le=65535)
    service_name: str | None = None
    sid: str | None = None
    username: str
    password: SecretStr
    is_sysdba: bool = False


@dataclass(frozen=True)
class MemoryAllocation:
    """One named allocation within an Oracle memory area."""

    name: str
    bytes: int


class OracleDriver:
    """Open Oracle database sessions."""

    def __init__(self, config: OracleConnectionConfig) -> None:
        """Initialize the driver with validated connection settings."""
        self._config = config

    @contextmanager
    def session(self) -> Generator[oracledb.Connection, None, None]:
        """Yield an active Oracle connection."""
        if self._config.service_name:
            dsn = oracledb.makedsn(self._config.hostname, self._config.port, service_name=self._config.service_name)
        elif self._config.sid:
            dsn = oracledb.makedsn(self._config.hostname, self._config.port, sid=self._config.sid)
        else:
            dsn = f"{self._config.hostname}:{self._config.port}"
        mode = oracledb.SYSDBA if self._config.is_sysdba or self._config.username.upper() == "SYS" else 0
        with oracledb.connect(user=self._config.username, password=self._config.password.get_secret_value(), dsn=dsn, mode=mode) as connection:
            yield connection


class MemoryRepository:
    """Read SGA and PGA allocations from Oracle dynamic performance views."""

    def __init__(self, connection: oracledb.Connection) -> None:
        """Initialize the repository with an active connection."""
        self._connection = connection

    def database_name(self) -> str:
        """Return the current database name."""
        return str(self._scalar("SELECT SYS_CONTEXT('USERENV', 'DB_NAME') FROM dual") or "<unknown>")

    def sga_total(self) -> int:
        """Return total SGA bytes."""
        return int(self._scalar("SELECT SUM(value) FROM v$sga") or 0)

    def sga_allocations(self) -> dict[str, list[MemoryAllocation]]:
        """Return SGA allocations grouped by pool."""
        sql = """
            SELECT NVL(pool, '(fixed)') AS pool, name, SUM(bytes) AS bytes
            FROM v$sgastat
            GROUP BY NVL(pool, '(fixed)'), name
            ORDER BY pool, bytes DESC, name
        """
        grouped: dict[str, list[MemoryAllocation]] = defaultdict(list)
        with self._connection.cursor() as cursor:
            cursor.execute(sql)
            for pool, name, size_bytes in cursor:
                grouped[str(pool)].append(MemoryAllocation(str(name), int(size_bytes)))
        return dict(grouped)

    def pga_allocations(self) -> list[MemoryAllocation]:
        """Return byte-valued PGA aggregate statistics."""
        sql = """
            SELECT name, value
            FROM v$pgastat
            WHERE unit = 'bytes'
            ORDER BY value DESC, name
        """
        with self._connection.cursor() as cursor:
            cursor.execute(sql)
            return [MemoryAllocation(str(name), int(value)) for name, value in cursor]

    def _scalar(self, sql: str) -> object | None:
        """Execute a query and return its first column."""
        with self._connection.cursor() as cursor:
            cursor.execute(sql)
            row = cursor.fetchone()
        return row[0] if row else None


def format_bytes(size_bytes: int) -> str:
    """Format a byte count using binary units."""
    value = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024 or unit == "TiB":
            return f"{value:,.2f} {unit}"
        value /= 1024
    return f"{value:,.2f} TiB"


def node_label(name: str, size_bytes: int, parent_bytes: int | None = None) -> Text:
    """Build a tree node label with size and optional parent percentage."""
    label = Text(name, style="bold")
    label.append(f"  {format_bytes(size_bytes)}", style="cyan")
    if parent_bytes:
        label.append(f"  ({size_bytes / parent_bytes * 100:.2f}% of parent)", style="dim")
    return label


def build_sga_tree(total_bytes: int, allocations: dict[str, list[MemoryAllocation]], min_bytes: int = 0) -> Tree:
    """Build an SGA pool and allocation tree."""
    tree = Tree(node_label("SGA", total_bytes))
    for pool, children in sorted(allocations.items(), key=lambda item: (-sum(child.bytes for child in item[1]), item[0])):
        pool_bytes = sum(child.bytes for child in children)
        pool_node = tree.add(node_label(pool, pool_bytes, total_bytes))
        visible = [child for child in children if child.bytes >= min_bytes]
        for child in sorted(visible, key=lambda item: (-item.bytes, item.name)):
            pool_node.add(node_label(child.name, child.bytes, pool_bytes))
        hidden_bytes = pool_bytes - sum(child.bytes for child in visible)
        if hidden_bytes:
            pool_node.add(node_label(f"Other ({len(children) - len(visible)} allocations below threshold)", hidden_bytes, pool_bytes))
    return tree


def build_pga_tree(allocations: list[MemoryAllocation], min_bytes: int = 0) -> Tree:
    """Build a PGA aggregate-statistics tree."""
    total = next((item.bytes for item in allocations if item.name.lower() == "total pga allocated"), 0)
    if not total:
        total = max((item.bytes for item in allocations), default=0)
    tree = Tree(node_label("PGA", total))
    visible = [item for item in allocations if item.bytes >= min_bytes and item.name.lower() != "total pga allocated"]
    for item in sorted(visible, key=lambda allocation: (-allocation.bytes, allocation.name)):
        tree.add(node_label(item.name, item.bytes, total))
    return tree


def build_display(database_name: str, sga_tree: Tree, pga_tree: Tree) -> Panel:
    """Build the complete memory report."""
    return Panel(Group(sga_tree, Text(), pga_tree), title=f"Oracle Memory Tree: {database_name}", border_style="blue")


class TyperApp(typer.Typer):
    """Typer application with parse_args support for tests and callers."""

    def parse_args(self, args: Sequence[str] | None = None) -> SimpleNamespace:
        """Parse command-line arguments into a namespace."""
        command = typer.main.get_command(self)
        context = command.make_context("memory-tree", list(args) if args is not None else sys.argv[1:])
        return SimpleNamespace(**context.params)


app = TyperApp(add_completion=False, help="Display Oracle SGA and PGA usage as terminal trees.")


@app.command()
def run(
    host: str = typer.Option("localhost", "--host", envvar="ORACLE_HOST", help="Oracle database host"),
    port: int = typer.Option(1521, "--port", envvar="ORACLE_PORT", help="Oracle database port"),
    service_name: str | None = typer.Option(None, "--service-name", envvar="ORACLE_SERVICE_NAME", help="Oracle service name"),
    sid: str | None = typer.Option(None, "--sid", envvar="ORACLE_SID", help="Oracle SID"),
    user: str | None = typer.Option(None, "--user", envvar="ORACLE_USER", help="Database username"),
    password: str | None = typer.Option(None, "--password", envvar="ORACLE_PASSWORD", help="Database password"),
    sysdba: bool = typer.Option(False, "--sysdba", help="Connect with SYSDBA privilege"),
    min_mb: float = typer.Option(0.0, "--min-mb", min=0, help="Group allocations smaller than this many MiB"),
) -> int:
    """Connect to Oracle and print the memory trees."""
    if not user or not password:
        logger.error("database username and password are required via flags or ORACLE_USER/ORACLE_PASSWORD")
        return 1
    if not service_name and not sid:
        logger.error("either --service-name or --sid is required")
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
        )
        with OracleDriver(config).session() as connection:
            repository = MemoryRepository(connection)
            threshold = int(min_mb * 1024 * 1024)
            display = build_display(
                repository.database_name(),
                build_sga_tree(repository.sga_total(), repository.sga_allocations(), threshold),
                build_pga_tree(repository.pga_allocations(), threshold),
            )
            Console().print(display)
    except (ValidationError, oracledb.DatabaseError) as exc:
        logger.error("Oracle memory report failed: {}", exc)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line entrypoint."""
    try:
        result = app(args=list(argv) if argv is not None else None, standalone_mode=False)
        return 0 if result is None else int(result)
    except typer.Exit as exc:
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
