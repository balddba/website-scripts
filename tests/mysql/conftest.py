"""Pytest fixtures for MySQL catalog integration tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from tests.mysql.blocking import BlockingPair, blocking_row_lock
from tests.mysql.bootstrap import FixtureObjects, bootstrap_fixture_objects, drop_fixture_objects
from tests.mysql.report import MySQLScriptReporter
from tests.mysql.script_runner import ScriptResult, mysql_connection, run_script
from tests.mysql.settings import MySQLTestSettings

RunMySQLSql = Callable[[str], ScriptResult]


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add the MySQL script report output option."""
    parser.addoption(
        "--mysql-report",
        default="reports/mysql-script-report.html",
        help="Path for the full MySQL script output report",
    )


@pytest.fixture(scope="session", autouse=True)
def mysql_script_reporter(request: pytest.FixtureRequest) -> Iterator[MySQLScriptReporter]:
    """Collect MySQL script output and write it after the test session."""
    reporter = MySQLScriptReporter(Path(request.config.getoption("--mysql-report")))
    yield reporter
    report_path = reporter.write()
    terminal_reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if terminal_reporter is not None:
        terminal_reporter.write_line(f"MySQL script report: {report_path.resolve()}")


@pytest.fixture(scope="session")
def mysql_settings() -> MySQLTestSettings:
    """Load MySQL test settings or skip if not configured in environment.

    Returns:
        MySQLTestSettings: Validated MySQL connection settings.

    Raises:
        pytest.skip.Exception: If MYSQL_TEST_USER or MYSQL_TEST_PASSWORD is not set.
    """
    settings = MySQLTestSettings.from_env()
    if settings is None:
        pytest.skip("MYSQL_TEST_USER and MYSQL_TEST_PASSWORD must be set in .env")
    return settings


@pytest.fixture(scope="session")
def fixture_objects(mysql_settings: MySQLTestSettings) -> Iterator[FixtureObjects]:
    """Create disposable schema objects used by MySQL integration tests."""
    with mysql_connection(mysql_settings) as connection:
        objects = bootstrap_fixture_objects(connection)
    yield objects
    with mysql_connection(mysql_settings) as connection:
        drop_fixture_objects(connection)


@pytest.fixture
def run_mysql_sql(
    request: pytest.FixtureRequest,
    mysql_settings: MySQLTestSettings,
    mysql_script_reporter: MySQLScriptReporter,
) -> RunMySQLSql:
    """Return a helper that runs one catalog SQL file on a fresh MySQL connection.

    Args:
        request (pytest.FixtureRequest): Current test request used to label report entries.
        mysql_settings (MySQLTestSettings): MySQL connection settings.
        mysql_script_reporter (MySQLScriptReporter): Session report collector.

    Returns:
        RunMySQLSql: Callable taking a script filename and returning ScriptResult.
    """

    def _run(script_name: str) -> ScriptResult:
        try:
            with mysql_connection(mysql_settings) as connection:
                result = run_script(connection, script_name)
        except Exception as exc:
            mysql_script_reporter.record_error(script_name, request.node.nodeid, exc)
            raise
        mysql_script_reporter.record_success(script_name, request.node.nodeid, result)
        return result

    return _run


@pytest.fixture
def blocking_lock(mysql_settings: MySQLTestSettings, fixture_objects: FixtureObjects) -> Iterator[BlockingPair]:
    """Yield blocker and waiter connection IDs while a row lock is held."""
    with blocking_row_lock(mysql_settings, fixture_objects) as pair:
        yield pair
