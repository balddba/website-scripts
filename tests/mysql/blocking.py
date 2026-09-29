"""Create a real InnoDB row-lock wait for blocking-script tests."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager

from pydantic import BaseModel, ConfigDict

from tests.mysql.bootstrap import FixtureObjects
from tests.mysql.script_runner import mysql_connection
from tests.mysql.settings import MySQLTestSettings


class BlockingPair(BaseModel):
    """Connection IDs participating in a test lock wait.

    Attributes:
        blocker_id (int): Connection ID holding the row lock.
        waiter_id (int): Connection ID waiting on the row lock.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    blocker_id: int
    waiter_id: int


@contextmanager
def blocking_row_lock(settings: MySQLTestSettings, objects: FixtureObjects) -> Iterator[BlockingPair]:
    """Hold one row lock while a second transaction waits for it.

    Args:
        settings (MySQLTestSettings): MySQL connection settings.
        objects (FixtureObjects): Fixture tables containing id=1.

    Yields:
        BlockingPair: Blocker and waiter connection IDs.

    Raises:
        TimeoutError: If the waiter does not appear as blocked within 10 seconds.
    """
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
            """Execute blocking update on the waiter session in a worker thread."""
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
    """Return the connection ID of an open MySQL session.

    Args:
        connection (object): Open MySQL connection with a cursor method.

    Returns:
        int: MySQL connection thread ID.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT CONNECTION_ID()")
        return int(cursor.fetchone()[0])


def _wait_until_blocked(connection: object, blocker_id: int, waiter_id: int) -> None:
    """Poll sys.innodb_lock_waits until waiter_id is waiting on blocker_id.

    Args:
        connection (object): Open MySQL probe connection.
        blocker_id (int): Blocking connection ID.
        waiter_id (int): Waiting connection ID.

    Raises:
        TimeoutError: If lock wait is not observed within the deadline.
    """
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
