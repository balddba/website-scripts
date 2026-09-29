"""Unit tests for the Oracle blocking-session monitor."""

from __future__ import annotations

from datetime import datetime
from io import StringIO
from unittest.mock import MagicMock

import oracledb
import pytest
from rich.console import Console

from oracle.python.blocks import (
    BlockingSession,
    BlockingSessionRepository,
    build_blocking_tree,
    build_display,
    build_parser,
    monitor,
    normalize_sql,
)


def session(**overrides) -> BlockingSession:
    """Build a representative blocking session."""
    values = {
        "instance_id": 1,
        "sid": 100,
        "serial_number": 200,
        "username": "APP_USER",
        "status": "ACTIVE",
        "machine": "app01",
        "program": "orders-api",
        "event": "enq: TX - row lock contention",
        "wait_seconds": 15,
        "sql_id": "abc123",
        "sql_text": "UPDATE orders SET status = 'SHIPPED' WHERE order_id = 42",
        "blocker_instance_id": None,
        "blocker_sid": None,
    }
    values.update(overrides)
    return BlockingSession(**values)


def render(value) -> str:
    """Render a Rich object to plain text for assertions."""
    output = StringIO()
    Console(file=output, force_terminal=False, width=160).print(value)
    return output.getvalue()


def test_normalize_sql_collapses_whitespace() -> None:
    """SQL should remain readable without preserving source whitespace."""
    assert normalize_sql("SELECT  *\n  FROM dual") == "SELECT * FROM dual"
    assert normalize_sql(None) == "<SQL text unavailable>"


def test_build_tree_renders_multilevel_chain_and_sql() -> None:
    """The tree should nest waiters and show SQL for every session."""
    blocker = session()
    waiter = session(
        sid=101,
        serial_number=201,
        sql_id="def456",
        sql_text="DELETE FROM order_items WHERE order_id = 42",
        blocker_instance_id=1,
        blocker_sid=100,
    )
    downstream = session(
        sid=102,
        serial_number=202,
        sql_id="ghi789",
        sql_text="UPDATE inventory SET reserved = reserved + 1",
        blocker_instance_id=1,
        blocker_sid=101,
    )

    output = render(build_blocking_tree([blocker, waiter, downstream]))

    assert "[BLOCKER]" in output
    assert output.count("[WAITER]") == 2
    assert "SQL [abc123]: UPDATE orders" in output
    assert "SQL [def456]: DELETE FROM order_items" in output
    assert "SQL [ghi789]: UPDATE inventory" in output


def test_build_display_handles_no_blockers() -> None:
    """An empty poll should clearly report that no sessions are blocked."""
    output = render(build_display("ORDERPROD", [], datetime(2026, 9, 28, 18, 0, 0)))
    assert "Database: ORDERPROD" in output
    assert "Sessions: 0" in output
    assert "No blocking sessions detected." in output


def test_repository_falls_back_to_local_views_once() -> None:
    """ORA-00942 on GV$ views should switch later polls to V$ views."""
    connection = MagicMock(spec=oracledb.Connection)
    cursor = MagicMock(spec=oracledb.Cursor)
    connection.cursor.return_value.__enter__.return_value = cursor
    error = oracledb.DatabaseError()
    error.args = (MagicMock(code=942),)
    cursor.execute.side_effect = [error, None, None]
    row = (1, 100, 200, "APP_USER", "ACTIVE", "app01", "orders-api", "enq: TX", 15, "abc123", "UPDATE orders SET status = 'X'", None, None)
    cursor.fetchall.side_effect = [[row], [row]]

    repository = BlockingSessionRepository(connection)
    first = repository.fetch()
    second = repository.fetch()

    assert first == second
    assert first[0].sid == 100
    executed = [call.args[0].lower() for call in cursor.execute.call_args_list]
    assert "from gv$session" in executed[0]
    assert "from v$session" in executed[1]
    assert "from v$session" in executed[2]


def test_repository_propagates_non_privilege_errors() -> None:
    """Unexpected Oracle errors should not be hidden by fallback logic."""
    connection = MagicMock(spec=oracledb.Connection)
    cursor = MagicMock(spec=oracledb.Cursor)
    connection.cursor.return_value.__enter__.return_value = cursor
    error = oracledb.DatabaseError()
    error.args = (MagicMock(code=3113),)
    cursor.execute.side_effect = error

    with pytest.raises(oracledb.DatabaseError):
        BlockingSessionRepository(connection).fetch()


def test_monitor_honors_bounded_iterations(monkeypatch) -> None:
    """Bounded polling should fetch exactly the requested number of frames."""
    repository = MagicMock(spec=BlockingSessionRepository)
    repository.fetch.return_value = []
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=120)
    monkeypatch.setattr("oracle.python.blocks.time.sleep", lambda _interval: None)

    monitor(repository, "ORDERPROD", console, interval=0.1, iterations=2)

    assert repository.fetch.call_count == 2
    assert output.getvalue().count("No blocking sessions detected.") == 2


def test_parser_defaults_to_continuous_two_second_polling() -> None:
    """CLI defaults should provide a useful continuous monitor."""
    args = build_parser().parse_args([])
    assert args.interval == 2.0
    assert args.iterations == 0
    assert args.once is False
