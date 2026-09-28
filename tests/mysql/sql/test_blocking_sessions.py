"""Integration test for mysql/sql/blocking_sessions.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_blocking_sessions(run_mysql_sql) -> None:
    """Execute blocking_sessions.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "blocking_sessions.sql")
