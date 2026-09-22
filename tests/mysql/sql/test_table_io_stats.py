"""Integration test for mysql/sql/table_io_stats.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_table_io_stats(run_mysql_sql) -> None:
    """Execute table_io_stats.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "table_io_stats.sql")
