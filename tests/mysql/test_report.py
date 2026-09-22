"""Tests for the MySQL script HTML report."""

from tests.mysql.report import MySQLScriptReporter, ScriptReportEntry, render_html
from tests.mysql.script_runner import QueryResult, ScriptResult


def test_render_html_includes_full_escaped_results() -> None:
    """Render every row and escape database values for safe HTML."""
    result = ScriptResult(
        statements=["select value from example"],
        queries=[QueryResult(columns=["VALUE"], rows=[("first",), ("<second>",), (None,)])],
    )

    report = render_html([ScriptReportEntry("example.sql", "test_example", result=result)])

    assert "Result set 1 (3 rows)" in report
    assert "first" in report
    assert "&lt;second&gt;" in report
    assert "NULL" in report


def test_render_html_includes_execution_errors() -> None:
    """Include failed script errors in the report."""
    report = render_html([ScriptReportEntry("broken.sql", "test_broken", error="missing <table>")])

    assert "Failed" in report
    assert "missing &lt;table&gt;" in report


def test_reporter_writes_an_empty_report(tmp_path) -> None:
    """Create a useful report even when all MySQL tests are skipped."""
    output_path = tmp_path / "report.html"

    MySQLScriptReporter(output_path).write()

    assert output_path.exists()
    assert "No MySQL scripts were executed" in output_path.read_text()
