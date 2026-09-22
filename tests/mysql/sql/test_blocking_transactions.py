"""Integration test for mysql/sql/blocking_transactions.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_blocking_transactions(run_mysql_sql, blocking_lock, fixture_objects) -> None:
    """Report a real waiting transaction and its blocker."""
    result = run_catalog_script(run_mysql_sql, "blocking_transactions.sql")
    query = result.queries[0]
    waiting_index = query.column_index("waiting_pid")
    blocking_index = query.column_index("blocking_pid")
    table_index = query.column_index("locked_table")

    assert any(
        int(row[waiting_index]) == blocking_lock.waiter_id
        and int(row[blocking_index]) == blocking_lock.blocker_id
        and fixture_objects.lock_table in str(row[table_index])
        for row in query.rows
    )
