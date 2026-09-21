"""Induce a TX row lock between two Oracle sessions."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import oracledb
from loguru import logger

from tests.oracle.bootstrap import FixtureObjects
from tests.oracle.script_runner import oracle_connection
from tests.oracle.settings import OracleTestSettings

_POLL_SECONDS = 15.0
_POLL_INTERVAL = 0.1


@dataclass(frozen=True)
class BlockingPair:
    """SIDs of a blocker session and the session waiting on it.

    Attributes:
        blocker_sid (int): SID holding the uncommitted row lock.
        waiter_sid (int): SID waiting on that lock.
    """

    blocker_sid: int
    waiter_sid: int


@contextmanager
def blocking_row_lock(settings: OracleTestSettings, objects: FixtureObjects) -> Iterator[BlockingPair]:
    """Hold an uncommitted UPDATE so a second session waits on the same row.

    Args:
        settings (OracleTestSettings): Connection settings.
        objects (FixtureObjects): Fixture table that contains id=1.

    Yields:
        BlockingPair: Blocker and waiter SIDs once GV$SESSION shows the wait.

    Raises:
        TimeoutError: If the waiter does not appear as blocked within the poll window.
        oracledb.DatabaseError: If setup statements fail.
    """
    update_sql = f"UPDATE {objects.schema}.{objects.table} SET payload = payload WHERE id = 1"
    waiter_error: list[BaseException] = []
    with oracle_connection(settings) as blocker, oracle_connection(settings) as waiter, oracle_connection(settings) as probe:
        blocker_sid = session_sid(blocker)
        waiter_sid = session_sid(waiter)
        with blocker.cursor() as cursor:
            try:
                cursor.execute(update_sql)
            except oracledb.DatabaseError as exc:
                logger.bind(sid=blocker_sid).error("sql_execute_failed err={}", exc)
                raise

        def wait_on_row() -> None:
            try:
                with waiter.cursor() as cursor:
                    cursor.execute(update_sql)
                waiter.rollback()
            except oracledb.DatabaseError as exc:
                waiter_error.append(exc)

        thread = threading.Thread(target=wait_on_row, name="oracle-lock-waiter", daemon=True)
        thread.start()
        try:
            _wait_until_blocked(probe, blocker_sid, waiter_sid)
            yield BlockingPair(blocker_sid=blocker_sid, waiter_sid=waiter_sid)
        finally:
            blocker.rollback()
            thread.join(timeout=_POLL_SECONDS)
            waiter.rollback()
    if waiter_error:
        raise waiter_error[0]


def session_sid(connection: oracledb.Connection) -> int:
    """Return the SID of the current session.

    Args:
        connection (oracledb.Connection): Open connection.

    Returns:
        int: Session identifier.

    Raises:
        oracledb.DatabaseError: If the SID query fails.
        RuntimeError: If the SID query returns no row.
    """
    with connection.cursor() as cursor:
        try:
            cursor.execute("SELECT SYS_CONTEXT('USERENV', 'SID') FROM dual")
        except oracledb.DatabaseError as exc:
            logger.error("sql_execute_failed err={}", exc)
            raise
        row = cursor.fetchone()
    if not row or row[0] is None:
        raise RuntimeError("Could not read USERENV SID")
    return int(row[0])


def _wait_until_blocked(connection: oracledb.Connection, blocker_sid: int, waiter_sid: int) -> None:
    """Poll V$SESSION until the waiter reports the blocker.

    Args:
        connection (oracledb.Connection): Probe session used only for polling.
        blocker_sid (int): Expected BLOCKING_SESSION value.
        waiter_sid (int): Waiting session SID.

    Raises:
        TimeoutError: If the wait is not visible before the timeout.
        oracledb.DatabaseError: If the poll query fails.
    """
    deadline = time.monotonic() + _POLL_SECONDS
    with connection.cursor() as cursor:
        while time.monotonic() < deadline:
            try:
                cursor.execute(
                    """
                    SELECT blocking_session
                    FROM v$session
                    WHERE sid = :waiter_sid
                    """,
                    {"waiter_sid": waiter_sid},
                )
            except oracledb.DatabaseError as exc:
                logger.error("sql_execute_failed err={}", exc)
                raise
            row = cursor.fetchone()
            if row and row[0] is not None and int(row[0]) == blocker_sid:
                return
            time.sleep(_POLL_INTERVAL)
    raise TimeoutError(f"Session {waiter_sid} did not wait on blocker {blocker_sid} within {_POLL_SECONDS}s")
