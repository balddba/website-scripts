"""Integration test for mysql/sql/instance_info.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_instance_info(run_mysql_sql) -> None:
    """Execute instance_info.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "instance_info.sql")
