"""Create a real InnoDB row-lock wait for blocking-script tests."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass

from tests.mysql.bootstrap import FixtureObjects
from tests.mysql.script_runner import mysql_connection
from tests.mysql.settings import MySQLTestSettings


@dataclass(frozen=True)
class BlockingPair:
    """Connection IDs participating in a test lock wait."""

    blocker_id: int
    waiter_id: int


@contextmanager
def blocking_row_lock(settings: MySQLTestSettings, objects: FixtureObjects) -> Iterator[BlockingPair]:
    """Hold one row lock while a second transaction waits for it."""
    with ExitStack() as stack:
        blocker = stack.enter_context(mysql_connection(settings))
        waiter = stack.enter_context(mysql_connection(settings))
        probe = stack.enter_context(mysql_connection(settings))
        blocker.autocommit(False)
        waiter.autocommit(False)

        blocker_id = _connection_id(blocker)
        waiter_id = _connection_id(waiter)
        target = f"`{objects.schema}`.`{objects.lock_table}`"
        with blocker.cursor() as cursor:
            cursor.execute(f"UPDATE {target} SET payload = 'blocked' WHERE id = 1")

        waiter_errors: list[BaseException] = []

        def wait_on_row() -> None:
            try:
                with waiter.cursor() as cursor:
                    cursor.execute(f"UPDATE {target} SET payload = 'waiting' WHERE id = 1")
            except BaseException as exc:
                waiter_errors.append(exc)

        thread = threading.Thread(target=wait_on_row, name="mysql-lock-waiter", daemon=True)
        thread.start()
        try:
            _wait_until_blocked(probe, blocker_id, waiter_id)
            yield BlockingPair(blocker_id=blocker_id, waiter_id=waiter_id)
        finally:
            blocker.rollback()
            thread.join(timeout=5)
            waiter.rollback()
        if waiter_errors:
            raise waiter_errors[0]


def _connection_id(connection: object) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT CONNECTION_ID()")
        return int(cursor.fetchone()[0])


def _wait_until_blocked(connection: object, blocker_id: int, waiter_id: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM sys.innodb_lock_waits WHERE waiting_pid = %s AND blocking_pid = %s",
                (waiter_id, blocker_id),
            )
            if int(cursor.fetchone()[0]) == 1:
                return
        time.sleep(0.05)
    raise TimeoutError(f"MySQL connection {waiter_id} did not block behind {blocker_id}")
