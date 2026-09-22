"""Integration test for mysql/sql/connection_stats.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_connection_stats(run_mysql_sql) -> None:
    """Execute connection_stats.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "connection_stats.sql")
