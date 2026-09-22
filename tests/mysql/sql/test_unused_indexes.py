"""Integration test for mysql/sql/unused_indexes.sql."""

import pytest

from tests.mysql.sql.harness import run_catalog_script


@pytest.mark.mysql
def test_unused_indexes(run_mysql_sql, fixture_objects) -> None:
    """Report the deliberately unused index on the fixture table."""
    result = run_catalog_script(run_mysql_sql, "unused_indexes.sql")
    query = result.queries[0]
    schema_index = query.column_index("schema_name")
    table_index = query.column_index("table_name")
    name_index = query.column_index("index_name")

    assert any(
        row[schema_index] == fixture_objects.schema
        and row[table_index] == fixture_objects.index_table
        and row[name_index] == fixture_objects.unused_index
        for row in query.rows
    )
