"""Integration test for mysql/sql/table_inventory.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_table_inventory(run_mysql_sql) -> None:
    """Execute table_inventory.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "table_inventory.sql")
