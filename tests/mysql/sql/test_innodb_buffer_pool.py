"""Integration test for mysql/sql/innodb_buffer_pool.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_innodb_buffer_pool(run_mysql_sql) -> None:
    """Execute innodb_buffer_pool.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "innodb_buffer_pool.sql")
