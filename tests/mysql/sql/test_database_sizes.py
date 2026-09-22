"""Integration test for mysql/sql/database_sizes.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_database_sizes(run_mysql_sql) -> None:
    """Execute database_sizes.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "database_sizes.sql")
