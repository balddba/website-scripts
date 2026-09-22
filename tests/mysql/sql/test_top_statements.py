"""Integration test for mysql/sql/top_statements.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_top_statements(run_mysql_sql) -> None:
    """Execute top_statements.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "top_statements.sql")
