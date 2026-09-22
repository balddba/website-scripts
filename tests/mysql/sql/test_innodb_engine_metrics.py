"""Integration test for mysql/sql/innodb_engine_metrics.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_innodb_engine_metrics(run_mysql_sql) -> None:
    """Execute innodb_engine_metrics.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "innodb_engine_metrics.sql")
