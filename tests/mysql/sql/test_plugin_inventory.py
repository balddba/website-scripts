"""Integration test for mysql/sql/plugin_inventory.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_plugin_inventory(run_mysql_sql) -> None:
    """Execute plugin_inventory.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "plugin_inventory.sql")
