"""Integration test for mysql/sql/innodb_configuration.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_innodb_configuration(run_mysql_sql) -> None:
    """Execute innodb_configuration.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "innodb_configuration.sql")
