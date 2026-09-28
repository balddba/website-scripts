"""Integration test for mysql/sql/user_details.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_user_details(run_mysql_sql) -> None:
    """Execute user_details.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "user_details.sql")
