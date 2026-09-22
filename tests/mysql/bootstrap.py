"""Create disposable schema objects used by MySQL integration tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TEST_SCHEMA = "website_scripts_test"
LOCK_TABLE = "ws_lock_probe"
INDEX_TABLE = "ws_index_probe"
UNUSED_INDEX = "idx_ws_unused_marker"


@dataclass(frozen=True)
class FixtureObjects:
    """Names of disposable MySQL objects created for integration tests."""

    schema: str = TEST_SCHEMA
    lock_table: str = LOCK_TABLE
    index_table: str = INDEX_TABLE
    unused_index: str = UNUSED_INDEX


def bootstrap_fixture_objects(connection: Any) -> FixtureObjects:
    """Create and seed deterministic tables for catalog-script assertions."""
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
        cursor.execute(
            f"INSERT INTO `{TEST_SCHEMA}`.`{LOCK_TABLE}` (id, payload) VALUES (1, 'ready') "
            "ON DUPLICATE KEY UPDATE payload = VALUES(payload)"
        )
        cursor.execute(
            f"INSERT INTO `{TEST_SCHEMA}`.`{INDEX_TABLE}` (id, marker, payload) VALUES (1, 'unused', 'fixture') "
            "ON DUPLICATE KEY UPDATE marker = VALUES(marker), payload = VALUES(payload)"
        )
    return FixtureObjects()


def drop_fixture_objects(connection: Any) -> None:
    """Drop the disposable integration-test schema."""
    with connection.cursor() as cursor:
        cursor.execute(f"DROP DATABASE IF EXISTS `{TEST_SCHEMA}`")
