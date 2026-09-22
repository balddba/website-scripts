"""Execute parsed MySQL catalog SQL scripts."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from tests.mysql.script_parser import ParsedMySQLScript, parse_mysql_script
from tests.mysql.settings import MySQLTestSettings

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = REPO_ROOT / "mysql" / "sql"


@dataclass(frozen=True)
class QueryResult:
    """One SELECT result set from a MySQL catalog script.

    Attributes:
        columns (list[str]): Column names from the cursor description.
        rows (list[tuple[object, ...]]): Fetched rows.
    """

    columns: list[str]
    rows: list[tuple[object, ...]]

    def column_index(self, name: str) -> int:
        """Return the index of a column, matching case-insensitively.

        Args:
            name (str): Column name to find.

        Returns:
            int: Zero-based column index.

        Raises:
            KeyError: If the column is not in the result.
        """
        needle = name.upper()
        for index, column in enumerate(self.columns):
            if column.upper() == needle:
                return index
        raise KeyError(name)

    def values(self, name: str) -> list[object]:
        """Return every value in a named column.

        Args:
            name (str): Column name to collect.

        Returns:
            list[object]: Values from each row for that column.
        """
        index = self.column_index(name)
        return [row[index] for row in self.rows]


@dataclass
class ScriptResult:
    """Outcome of running a MySQL catalog SQL script.

    Attributes:
        statements (list[str]): Statements that were executed.
        queries (list[QueryResult]): SELECT result sets in execution order.
    """

    statements: list[str]
    queries: list[QueryResult] = field(default_factory=list)


@contextmanager
def mysql_connection(settings: MySQLTestSettings) -> Iterator[Any]:
    """Open a MySQL connection and close it when done.

    Supports pymysql or mysql.connector.

    Args:
        settings (MySQLTestSettings): Validated connection settings.

    Yields:
        Any: Open database connection.

    Raises:
        ImportError: If no MySQL driver (pymysql or mysql.connector) is installed.
        Exception: If connection fails.
    """
    password = settings.password.get_secret_value()
    conn = None

    try:
        import pymysql

        conn = pymysql.connect(
            host=settings.host,
            port=settings.port,
            user=settings.user,
            password=password,
            database=settings.database,
            autocommit=True,
        )
    except ImportError:
        try:
            import mysql.connector

            conn = mysql.connector.connect(
                host=settings.host,
                port=settings.port,
                user=settings.user,
                password=password,
                database=settings.database,
                autocommit=True,
            )
        except ImportError as exc:
            logger.error("No MySQL driver available. Install pymysql or mysql-connector-python.")
            raise ImportError("Neither pymysql nor mysql-connector-python is installed.") from exc

    try:
        yield conn
    finally:
        conn.close()


def run_script(
    connection: Any,
    script_name: str,
) -> ScriptResult:
    """Parse a MySQL catalog SQL file and execute its statements.

    Args:
        connection (Any): Open MySQL database connection.
        script_name (str): Filename under mysql/sql/.

    Returns:
        ScriptResult: Result sets and executed statements.

    Raises:
        FileNotFoundError: If the SQL file does not exist.
    """
    path = SQL_DIR / script_name
    parsed = parse_mysql_script(path.read_text())
    return execute_parsed(connection, parsed)


def execute_parsed(
    connection: Any,
    parsed: ParsedMySQLScript,
) -> ScriptResult:
    """Execute parsed statements on an open MySQL connection.

    Args:
        connection (Any): Open MySQL database connection.
        parsed (ParsedMySQLScript): Parsed script model.

    Returns:
        ScriptResult: Result sets and executed statements.
    """
    queries: list[QueryResult] = []
    executed: list[str] = []

    with connection.cursor() as cursor:
        for statement in parsed.statements:
            executed.append(statement)
            try:
                cursor.execute(statement)
            except Exception as exc:
                logger.error("mysql_execute_failed err={} sql={}", exc, statement[:300])
                raise

            if cursor.description:
                columns = [col[0] for col in cursor.description]
                rows = [tuple(row) for row in cursor.fetchall()]
                queries.append(QueryResult(columns=columns, rows=rows))

    return ScriptResult(statements=executed, queries=queries)
