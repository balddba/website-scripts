"""Integration test for mysql/sql/table_sizes.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_table_sizes(run_mysql_sql) -> None:
    """Execute table_sizes.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "table_sizes.sql")
