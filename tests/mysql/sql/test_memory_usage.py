"""Integration test for mysql/sql/memory_usage.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_memory_usage(run_mysql_sql) -> None:
    """Execute memory_usage.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "memory_usage.sql")
