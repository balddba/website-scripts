"""Tests for the Oracle script HTML report."""

from tests.oracle.report import OracleScriptReporter, ScriptReportEntry, render_html
from tests.oracle.script_runner import QueryResult, ScriptResult


def test_render_html_includes_full_escaped_results() -> None:
    """Render every row and escape database values for safe HTML."""
    result = ScriptResult(
        statements=["select value from example"],
        queries=[QueryResult(columns=["VALUE"], rows=[("first",), ("<second>",), (None,)])],
        dbms_output=["completed & checked"],
    )

    report = render_html([ScriptReportEntry("example.sql", "test_example", result=result)])

    assert "Result set 1 (3 rows)" in report
    assert "first" in report
    assert "&lt;second&gt;" in report
    assert "NULL" in report
    assert "completed &amp; checked" in report


def test_render_html_includes_execution_errors() -> None:
    """Include failed script errors in the report."""
    report = render_html([ScriptReportEntry("broken.sql", "test_broken", error="ORA-00942: missing <table>")])

    assert "Failed" in report
    assert "ORA-00942: missing &lt;table&gt;" in report


def test_reporter_writes_an_empty_report(tmp_path) -> None:
    """Create a useful report even when all Oracle tests are skipped."""
    output_path = tmp_path / "report.html"

    OracleScriptReporter(output_path).write()

    assert output_path.exists()
    assert "No Oracle scripts were executed" in output_path.read_text()
