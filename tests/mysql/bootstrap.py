"""Create disposable schema objects used by MySQL integration tests."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

TEST_SCHEMA = "website_scripts_test"
LOCK_TABLE = "ws_lock_probe"
INDEX_TABLE = "ws_index_probe"
UNUSED_INDEX = "idx_ws_unused_marker"


class FixtureObjects(BaseModel):
    """Names of disposable MySQL objects created for integration tests.

    Attributes:
        schema_name (str): Database schema name.
        lock_table (str): Table name used for lock testing.
        index_table (str): Table name used for index testing.
        unused_index (str): Index name used for unused index testing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_name: str = Field(default=TEST_SCHEMA, alias="schema")
    lock_table: str = LOCK_TABLE
    index_table: str = INDEX_TABLE
    unused_index: str = UNUSED_INDEX

    @property
    def schema(self) -> str:
        """Return the schema name."""
        return self.schema_name


def bootstrap_fixture_objects(connection: Any) -> FixtureObjects:
    """Create and seed deterministic tables for catalog-script assertions.

    Args:
        connection (Any): Active database connection.

    Returns:
        FixtureObjects: Names of created fixture objects.
    """
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{TEST_SCHEMA}`")
        cursor.execute(
            f"""CREATE TABLE IF NOT EXISTS `{TEST_SCHEMA}`.`{LOCK_TABLE}` (
                id BIGINT PRIMARY KEY,
                payload VARCHAR(100) NOT NULL
            ) ENGINE=InnoDB"""
        )
        cursor.execute(
            f"""CREATE TABLE IF NOT EXISTS `{TEST_SCHEMA}`.`{INDEX_TABLE}` (
                id BIGINT PRIMARY KEY,
                marker VARCHAR(100) NOT NULL,
                payload VARCHAR(100) NOT NULL,
                INDEX `{UNUSED_INDEX}` (marker)
            ) ENGINE=InnoDB"""
        )
        cursor.execute(f"INSERT INTO `{TEST_SCHEMA}`.`{LOCK_TABLE}` (id, payload) VALUES (1, 'ready') ON DUPLICATE KEY UPDATE payload = VALUES(payload)")
        cursor.execute(f"INSERT INTO `{TEST_SCHEMA}`.`{INDEX_TABLE}` (id, marker, payload) VALUES (1, 'unused', 'fixture') ON DUPLICATE KEY UPDATE marker = VALUES(marker), payload = VALUES(payload)")
    return FixtureObjects()


def drop_fixture_objects(connection: Any) -> None:
    """Drop the disposable integration-test schema.

    Args:
        connection (Any): Active database connection.
    """
    with connection.cursor() as cursor:
        cursor.execute(f"DROP DATABASE IF EXISTS `{TEST_SCHEMA}`")
