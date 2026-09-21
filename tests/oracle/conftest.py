"""Pytest fixtures for Oracle catalog integration tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from tests.oracle.blocking import BlockingPair, blocking_row_lock
from tests.oracle.bootstrap import FixtureObjects, bootstrap_fixture_objects
from tests.oracle.report import OracleScriptReporter
from tests.oracle.script_runner import ScriptResult, oracle_connection, run_script
from tests.oracle.settings import OracleTestSettings

RunOracleSql = Callable[..., ScriptResult]


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add the Oracle script report output option."""
    parser.addoption(
        "--oracle-report",
        default="reports/oracle-script-report.html",
        help="Path for the full Oracle script output report",
    )


@pytest.fixture(scope="session", autouse=True)
def oracle_script_reporter(request: pytest.FixtureRequest) -> Iterator[OracleScriptReporter]:
    """Collect Oracle script output and write it after the test session."""
    reporter = OracleScriptReporter(Path(request.config.getoption("--oracle-report")))
    yield reporter
    report_path = reporter.write()
    terminal_reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if terminal_reporter is not None:
        terminal_reporter.write_line(f"Oracle script report: {report_path.resolve()}")


@pytest.fixture(scope="session")
def oracle_settings() -> OracleTestSettings:
    """Load Oracle test settings or skip when they are not configured.

    Returns:
        OracleTestSettings: Validated connection settings.

    Raises:
        pytest.skip.Exception: If ORACLE_TEST_* is incomplete.
    """
    settings = OracleTestSettings.from_env()
    if settings is None:
        pytest.skip("ORACLE_TEST_USER, ORACLE_TEST_PASSWORD, ORACLE_TEST_CONNECT, and ORACLE_TEST_SCHEMA must be set")
    return settings


@pytest.fixture(scope="session")
def fixture_objects(oracle_settings: OracleTestSettings) -> FixtureObjects:
    """Create schema objects used by parameterized and lock tests.

    Args:
        oracle_settings (OracleTestSettings): Connection settings.

    Returns:
        FixtureObjects: Names of objects in ORACLE_TEST_SCHEMA.
    """
    with oracle_connection(oracle_settings) as connection:
        return bootstrap_fixture_objects(connection, oracle_settings)


@pytest.fixture
def run_oracle_sql(
    request: pytest.FixtureRequest,
    oracle_settings: OracleTestSettings,
    oracle_script_reporter: OracleScriptReporter,
) -> RunOracleSql:
    """Return a helper that runs one catalog SQL file on a fresh connection.

    Args:
        request (pytest.FixtureRequest): Current test request used to label report entries.
        oracle_settings (OracleTestSettings): Connection settings.
        oracle_script_reporter (OracleScriptReporter): Session report collector.

    Returns:
        RunOracleSql: Callable (script_name, args=None, defines=None) -> ScriptResult.
    """

    def _run(
        script_name: str,
        args: list[str] | None = None,
        defines: dict[str, str] | None = None,
    ) -> ScriptResult:
        try:
            with oracle_connection(oracle_settings) as connection:
                result = run_script(connection, script_name, args=args, defines=defines)
        except Exception as exc:
            oracle_script_reporter.record_error(script_name, request.node.nodeid, exc)
            raise
        oracle_script_reporter.record_success(script_name, request.node.nodeid, result)
        return result

    return _run


@pytest.fixture
def blocking_lock(oracle_settings: OracleTestSettings, fixture_objects: FixtureObjects) -> Iterator[BlockingPair]:
    """Yield blocker and waiter SIDs while a row lock is held.

    Args:
        oracle_settings (OracleTestSettings): Connection settings.
        fixture_objects (FixtureObjects): Fixture table with id=1.

    Yields:
        BlockingPair: SIDs to look up in blocking-session scripts.
    """
    with blocking_row_lock(oracle_settings, fixture_objects) as pair:
        yield pair
