"""Integration test for mysql/sql/source_replica_status.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_source_replica_status(run_mysql_sql) -> None:
    """Execute source_replica_status.sql against the test instance."""
    run_catalog_script(run_mysql_sql, "source_replica_status.sql")
