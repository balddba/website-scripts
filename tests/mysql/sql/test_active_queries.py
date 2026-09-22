"""Integration test for mysql/sql/active_queries.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_active_queries(run_mysql_sql) -> None:
    """Execute active_queries.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "active_queries.sql")
