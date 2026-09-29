#!/usr/bin/env python3
# ===============================================================================
#
# Script Name: blocks.py
# Title: Monitor Oracle blocking sessions
# Tags: Python, Performance, Locks, RAC
# Purpose: Poll Oracle and display blocking session chains with SQL text.
#
# Description:
#   Polls GV$SESSION and GV$SQL for current blocking relationships and renders
#   blockers and waiters as a live tree. Falls back to V$ views when GV$ views
#   are unavailable. Current or most recent SQL is shown for every session.
#
# Parameters:
#   Command-line Oracle connection and polling settings; use --help for details.
#
# Required Privileges:
#   - SELECT on GV$SESSION and GV$SQL, or V$SESSION and V$SQL
#   - Or SELECT_CATALOG_ROLE
#
# Output Format:
#   - Live terminal tree of blockers, waiters, wait details, and SQL text
#
# Example Usage:
#   python blocks.py --service-name ORCLPDB1 --user system --password secret
#   python blocks.py --service-name ORCLPDB1 --user system --password secret --once
#   python blocks.py --service-name ORCLPDB1 --user system --password secret --interval 5
#
# Author: Aaron Myers <aaron@balddba.com>
#
# ===============================================================================
"""Poll Oracle and display blocking session chains with SQL text."""

from __future__ import annotations

import sys
import time
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import oracledb
import typer
from loguru import logger
from pydantic import BaseModel, Field, SecretStr, ValidationError
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree

SessionKey = tuple[int, int]


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
class BlockingSession:
    """Session details needed to render one blocking-tree node."""

    instance_id: int
    sid: int
    serial_number: int
    username: str | None
    status: str
    machine: str | None
    program: str | None
    event: str | None
    wait_seconds: int
    sql_id: str | None
    sql_text: str | None
    blocker_instance_id: int | None
    blocker_sid: int | None

    @property
    def key(self) -> SessionKey:
        """Return the RAC-safe identity of this session."""
        return (self.instance_id, self.sid)

    @property
    def blocker_key(self) -> SessionKey | None:
        """Return the RAC-safe blocker identity, when present."""
        if self.blocker_instance_id is None or self.blocker_sid is None:
            return None
        return (self.blocker_instance_id, self.blocker_sid)


class OracleDriver:
    """Open Oracle database sessions."""

    def __init__(self, config: OracleConnectionConfig) -> None:
        """Initialize the driver with validated connection settings.

        Args:
            config (OracleConnectionConfig): Oracle connection settings and credentials.
        """
        self._config = config

    @contextmanager
    def session(self) -> Generator[oracledb.Connection, None, None]:
        """Yield an active Oracle connection.

        Yields:
            oracledb.Connection: Active Oracle database connection.
        """
        if self._config.service_name:
            dsn = oracledb.makedsn(self._config.hostname, self._config.port, service_name=self._config.service_name)
        elif self._config.sid:
            dsn = oracledb.makedsn(self._config.hostname, self._config.port, sid=self._config.sid)
        else:
            dsn = f"{self._config.hostname}:{self._config.port}"
        mode = oracledb.SYSDBA if self._config.is_sysdba or self._config.username.upper() == "SYS" else 0
        with oracledb.connect(
            user=self._config.username,
            password=self._config.password.get_secret_value(),
            dsn=dsn,
            mode=mode,
        ) as connection:
            yield connection


class BlockingSessionRepository:
    """Read current blocking relationships from Oracle dynamic views."""

    def __init__(self, connection: oracledb.Connection) -> None:
        """Initialize the repository with an active connection.

        Args:
            connection (oracledb.Connection): Active database connection.
        """
        self._connection = connection
        self._use_global_views = True

    def database_name(self) -> str:
        """Return the current database name.

        Returns:
            str: Database name or unknown indicator.
        """
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT SYS_CONTEXT('USERENV', 'DB_NAME') FROM dual")
            row = cursor.fetchone()
        return str(row[0]) if row and row[0] is not None else "<unknown>"

    def fetch(self) -> list[BlockingSession]:
        """Fetch sessions participating in blocking relationships.

        Returns:
            list[BlockingSession]: List of blocking and blocked sessions.
        """
        if self._use_global_views:
            try:
                rows = self._query(self._global_sql())
            except oracledb.DatabaseError as exc:
                error = exc.args[0] if exc.args else None
                if getattr(error, "code", 0) not in {942, 1031}:
                    raise
                logger.warning("GV$ views unavailable; falling back to V$SESSION and V$SQL")
                self._use_global_views = False
                rows = self._query(self._local_sql())
        else:
            rows = self._query(self._local_sql())
        return [self._row_to_session(row) for row in rows]

    def _query(self, sql: str) -> list[tuple[Any, ...]]:
        """Execute a blocking-session query.

        Args:
            sql (str): SQL query text to execute.

        Returns:
            list[tuple[Any, ...]]: List of fetched database rows.
        """
        with self._connection.cursor() as cursor:
            cursor.execute(sql)
            return list(cursor.fetchall())

    @staticmethod
    def _row_to_session(row: Sequence[Any]) -> BlockingSession:
        """Convert a database row into a blocking session.

        Args:
            row (Sequence[Any]): Database row values.

        Returns:
            BlockingSession: Structured blocking session model.
        """
        return BlockingSession(
            instance_id=int(row[0]),
            sid=int(row[1]),
            serial_number=int(row[2]),
            username=str(row[3]) if row[3] is not None else None,
            status=str(row[4]),
            machine=str(row[5]) if row[5] is not None else None,
            program=str(row[6]) if row[6] is not None else None,
            event=str(row[7]) if row[7] is not None else None,
            wait_seconds=int(row[8] or 0),
            sql_id=str(row[9]) if row[9] is not None else None,
            sql_text=str(row[10]).strip() if row[10] is not None else None,
            blocker_instance_id=int(row[11]) if row[11] is not None else None,
            blocker_sid=int(row[12]) if row[12] is not None else None,
        )

    @staticmethod
    def _global_sql() -> str:
        """Return the RAC-aware blocking-session query.

        Returns:
            str: SQL query text targeting GV$SESSION.
        """
        return """
            SELECT s.inst_id,
                   s.sid,
                   s.serial#,
                   s.username,
                   s.status,
                   s.machine,
                   s.program,
                   s.event,
                   s.seconds_in_wait,
                   COALESCE(s.sql_id, s.prev_sql_id) AS display_sql_id,
                   (SELECT DBMS_LOB.SUBSTR(q.sql_fulltext, 4000, 1)
                      FROM gv$sql q
                     WHERE q.inst_id = s.inst_id
                       AND q.sql_id = COALESCE(s.sql_id, s.prev_sql_id)
                       AND ROWNUM = 1) AS sql_text,
                   s.blocking_instance,
                   s.blocking_session
              FROM gv$session s
             WHERE s.blocking_session IS NOT NULL
                OR (s.inst_id, s.sid) IN (
                       SELECT blocked.blocking_instance, blocked.blocking_session
                         FROM gv$session blocked
                        WHERE blocked.blocking_session IS NOT NULL
                    )
             ORDER BY s.inst_id, s.sid
        """

    @staticmethod
    def _local_sql() -> str:
        """Return the single-instance blocking-session query.

        Returns:
            str: SQL query text targeting V$SESSION.
        """
        return """
            SELECT 1 AS inst_id,
                   s.sid,
                   s.serial#,
                   s.username,
                   s.status,
                   s.machine,
                   s.program,
                   s.event,
                   s.seconds_in_wait,
                   COALESCE(s.sql_id, s.prev_sql_id) AS display_sql_id,
                   (SELECT DBMS_LOB.SUBSTR(q.sql_fulltext, 4000, 1)
                      FROM v$sql q
                     WHERE q.sql_id = COALESCE(s.sql_id, s.prev_sql_id)
                       AND ROWNUM = 1) AS sql_text,
                   CASE WHEN s.blocking_session IS NOT NULL THEN 1 END AS blocking_instance,
                   s.blocking_session
              FROM v$session s
             WHERE s.blocking_session IS NOT NULL
                OR s.sid IN (
                       SELECT blocked.blocking_session
                         FROM v$session blocked
                        WHERE blocked.blocking_session IS NOT NULL
                    )
             ORDER BY s.sid
        """


def normalize_sql(sql_text: str | None) -> str:
    """Collapse SQL whitespace for compact terminal display.

    Args:
        sql_text (str | None): Raw SQL string to normalize.

    Returns:
        str: Cleaned and condensed single-line SQL text.
    """
    if not sql_text:
        return "<SQL text unavailable>"
    return " ".join(sql_text.split())


def session_label(session: BlockingSession, is_root: bool) -> Text:
    """Build a styled label for one session node.

    Args:
        session (BlockingSession): Session metadata to format.
        is_root (bool): True if the session is a root blocker.

    Returns:
        Text: Styled Rich text label.
    """
    role = "BLOCKER" if is_root else "WAITER"
    style = "bold red" if is_root else "bold yellow"
    user = session.username or "<background>"
    label = Text()
    label.append(f"[{role}] ", style=style)
    label.append(f"inst={session.instance_id} sid={session.sid},{session.serial_number} ", style="bold")
    label.append(f"user={user} status={session.status}")
    if not is_root:
        label.append(f" wait={session.wait_seconds}s")
    return label


def add_session_details(node: Tree, session: BlockingSession) -> None:
    """Attach wait, client, and SQL details to a session node.

    Args:
        node (Tree): Rich tree node to attach details to.
        session (BlockingSession): Session details to render.
    """
    if session.event:
        node.add(Text(f"Wait event: {session.event}"))
    client_parts = [part for part in (session.machine, session.program) if part]
    if client_parts:
        node.add(Text(f"Client: {' | '.join(client_parts)}"))
    sql_id = session.sql_id or "<none>"
    node.add(Text(f"SQL [{sql_id}]: {normalize_sql(session.sql_text)}", style="cyan"))


def build_blocking_tree(sessions: Sequence[BlockingSession]) -> Tree:
    """Build a forest of blocking chains beneath one Rich tree.

    Args:
        sessions (Sequence[BlockingSession]): Collection of active blocking sessions.

    Returns:
        Tree: Constructed Rich tree representation.
    """
    root = Tree(Text("Blocking Session Trees", style="bold"))
    by_key = {session.key: session for session in sessions}
    children: dict[SessionKey, list[BlockingSession]] = {}
    roots: list[BlockingSession] = []

    for session in sessions:
        blocker_key = session.blocker_key
        if blocker_key is not None and blocker_key in by_key and blocker_key != session.key:
            children.setdefault(blocker_key, []).append(session)
        else:
            roots.append(session)

    for values in children.values():
        values.sort(key=lambda item: (-item.wait_seconds, item.instance_id, item.sid))
    roots.sort(key=lambda item: (item.instance_id, item.sid))

    rendered: set[SessionKey] = set()

    def add_branch(parent: Tree, session: BlockingSession, ancestry: frozenset[SessionKey]) -> None:
        """Add a session branch and its descendants to the render tree.

        Args:
            parent (Tree): Parent tree node to attach to.
            session (BlockingSession): Blocking session to add.
            ancestry (frozenset[SessionKey]): Ancestor session keys to detect cycles.
        """
        is_root = session.blocker_key is None or session.blocker_key not in by_key
        node = parent.add(session_label(session, is_root=is_root))
        add_session_details(node, session)
        rendered.add(session.key)
        if session.key in ancestry:
            node.add(Text("Cycle detected; branch stopped.", style="bold red"))
            return
        next_ancestry = ancestry | {session.key}
        for child in children.get(session.key, []):
            add_branch(node, child, next_ancestry)

    for session in roots:
        add_branch(root, session, frozenset())

    # Corrupt or rapidly changing session state can leave a cycle with no root.
    for session in sessions:
        if session.key not in rendered:
            add_branch(root, session, frozenset())
    return root


def build_display(database_name: str, sessions: Sequence[BlockingSession], captured_at: datetime | None = None) -> RenderableType:
    """Build one complete monitor frame.

    Args:
        database_name (str): Current Oracle database name.
        sessions (Sequence[BlockingSession]): Collection of active blocking sessions.
        captured_at (datetime | None): Optional timestamp of capture.

    Returns:
        RenderableType: Rich renderable monitor display.
    """
    captured_at = captured_at or datetime.now().astimezone()
    header = Text(
        f"Database: {database_name}   Captured: {captured_at.strftime('%Y-%m-%d %H:%M:%S %Z')}   Sessions: {len(sessions)}",
        style="bold",
    )
    if not sessions:
        body: RenderableType = Text("No blocking sessions detected.", style="bold green")
    else:
        body = build_blocking_tree(sessions)
    return Group(header, Panel(body, border_style="red" if sessions else "green"))


def monitor(
    repository: BlockingSessionRepository,
    database_name: str,
    console: Console,
    interval: float,
    iterations: int,
) -> None:
    """Poll and render blocking sessions until stopped or complete.

    Args:
        repository (BlockingSessionRepository): Data access repository for blocking sessions.
        database_name (str): Name of target Oracle database.
        console (Console): Rich console instance for rendering.
        interval (float): Seconds to pause between iterations.
        iterations (int): Maximum poll count; 0 runs indefinitely.
    """
    if iterations == 1 or not console.is_terminal:
        completed = 0
        while iterations == 0 or completed < iterations:
            console.print(build_display(database_name, repository.fetch()))
            completed += 1
            if iterations == 0 or completed < iterations:
                time.sleep(interval)
        return

    completed = 0
    with Live(console=console, refresh_per_second=4, screen=False) as live:
        while iterations == 0 or completed < iterations:
            live.update(build_display(database_name, repository.fetch()), refresh=True)
            completed += 1
            if iterations == 0 or completed < iterations:
                time.sleep(interval)


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
        ctx = cmd.make_context("blocks", list(args) if args is not None else sys.argv[1:])
        return SimpleNamespace(**ctx.params)


app = TyperApp(add_completion=False, help="Poll Oracle and display blocking session trees with SQL text.")


@app.command()
def run(
    host: str = typer.Option("localhost", "--host", envvar="ORACLE_HOST", help="Oracle database host"),
    port: int = typer.Option(1521, "--port", envvar="ORACLE_PORT", help="Oracle database port"),
    service_name: str | None = typer.Option(None, "--service-name", envvar="ORACLE_SERVICE_NAME", help="Oracle service name"),
    sid: str | None = typer.Option(None, "--sid", envvar="ORACLE_SID", help="Oracle SID"),
    user: str | None = typer.Option(None, "--user", envvar="ORACLE_USER", help="Database username"),
    password: str | None = typer.Option(None, "--password", envvar="ORACLE_PASSWORD", help="Database password"),
    sysdba: bool = typer.Option(False, "--sysdba", help="Connect with SYSDBA privilege"),
    interval: float = typer.Option(2.0, "--interval", help="Seconds between polls (default: 2)"),
    iterations: int = typer.Option(0, "--iterations", help="Number of polls; 0 runs until interrupted (default: 0)"),
    once: bool = typer.Option(False, "--once", help="Poll once and exit"),
) -> int:
    """Run the blocking-session monitor.

    Args:
        host (str): Database hostname.
        port (int): Database port.
        service_name (str | None): Oracle service name.
        sid (str | None): Oracle SID.
        user (str | None): Database username.
        password (str | None): Database password.
        sysdba (bool): Connect with SYSDBA privilege.
        interval (float): Seconds between polls.
        iterations (int): Number of polls; 0 runs until interrupted.
        once (bool): Poll once and exit.

    Returns:
        int: Process exit code.
    """
    if not user or not password:
        logger.error("database username and password are required via flags or ORACLE_USER/ORACLE_PASSWORD")
        return 1
    if not service_name and not sid:
        logger.error("either --service-name or --sid is required")
        return 1
    if interval <= 0:
        logger.error("--interval must be greater than zero")
        return 1
    if iterations < 0:
        logger.error("--iterations cannot be negative")
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
    except ValidationError as exc:
        logger.error("Invalid connection configuration: {}", exc)
        return 1

    console = Console()
    try:
        with OracleDriver(config).session() as connection:
            repository = BlockingSessionRepository(connection)
            monitor(
                repository=repository,
                database_name=repository.database_name(),
                console=console,
                interval=interval,
                iterations=1 if once else iterations,
            )
    except KeyboardInterrupt:
        console.print("\nMonitoring stopped.", style="dim")
        return 0
    except oracledb.DatabaseError as exc:
        logger.error("Oracle operation failed: {}", exc)
        return 1
    return 0


def build_parser() -> TyperApp:
    """Build the command-line parser.

    Returns:
        TyperApp: Configured Typer application.
    """
    return app


def main(argv: Sequence[str] | None = None) -> int:
    """Run the blocking-session monitor entrypoint.

    Args:
        argv (Sequence[str] | None): Command-line arguments.

    Returns:
        int: Process exit code.
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
