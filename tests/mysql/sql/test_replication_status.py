"""Integration test for mysql/sql/replication_status.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_replication_status(run_mysql_sql) -> None:
    """Execute replication_status.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "replication_status.sql")
