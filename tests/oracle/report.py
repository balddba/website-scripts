"""Render complete Oracle script results as a self-contained HTML report."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from tests.oracle.script_runner import ScriptResult


class ScriptReportEntry(BaseModel):
    """One attempted catalog-script execution.

    Attributes:
        script_name (str): Catalog script filename.
        test_name (str): Pytest test node name.
        result (ScriptResult | None): Execution outcome when successful.
        error (str | None): Formatted error message when execution failed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    script_name: str
    test_name: str
    result: ScriptResult | None = None
    error: str | None = None

    def __init__(
        self,
        script_name: str,
        test_name: str,
        result: ScriptResult | None = None,
        error: str | None = None,
        **data: Any,
    ) -> None:
        """Initialize ScriptReportEntry.

        Args:
            script_name (str): Catalog script filename.
            test_name (str): Pytest test node name.
            result (ScriptResult | None): Execution outcome when successful.
            error (str | None): Formatted error message when execution failed.
            **data (Any): Additional keyword arguments.
        """
        super().__init__(script_name=script_name, test_name=test_name, result=result, error=error, **data)


class OracleScriptReporter:
    """Collect script executions and write their complete results at session end."""

    def __init__(self, output_path: Path) -> None:
        """Create a reporter targeting output_path.

        Args:
            output_path (Path): File path where the HTML report is saved.
        """
        self.output_path = output_path
        self.entries: list[ScriptReportEntry] = []

    def record_success(self, script_name: str, test_name: str, result: ScriptResult) -> None:
        """Record a successful script execution.

        Args:
            script_name (str): Catalog script filename.
            test_name (str): Pytest test node name.
            result (ScriptResult): Execution outcome.
        """
        self.entries.append(ScriptReportEntry(script_name=script_name, test_name=test_name, result=result))

    def record_error(self, script_name: str, test_name: str, error: BaseException) -> None:
        """Record a script execution that raised an exception.

        Args:
            script_name (str): Catalog script filename.
            test_name (str): Pytest test node name.
            error (BaseException): Exception raised during script execution.
        """
        self.entries.append(ScriptReportEntry(script_name=script_name, test_name=test_name, error=str(error)))

    def write(self) -> Path:
        """Write the report, including when no scripts were attempted.

        Returns:
            Path: Path to the generated HTML report file.
        """
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(render_html(self.entries), encoding="utf-8")
        return self.output_path


def render_html(entries: list[ScriptReportEntry]) -> str:
    """Return a self-contained HTML report for script entries.

    Args:
        entries (list[ScriptReportEntry]): Collected script execution entries.

    Returns:
        str: Rendered HTML document content.
    """
    generated_at = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
    successful = sum(entry.result is not None for entry in entries)
    failed = len(entries) - successful
    sections = "".join(_render_entry(entry) for entry in entries)
    if not sections:
        sections = "<p><strong>No Oracle scripts were executed.</strong> Check the pytest skip reasons and ORACLE_TEST_* settings.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Oracle script test report</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ margin: 0 auto; max-width: 1600px; padding: 24px; }}
    h1, h2, h3 {{ letter-spacing: 0; }}
    .summary {{ display: flex; gap: 24px; margin-bottom: 24px; }}
    .script {{ border-top: 1px solid #8888; padding: 20px 0; }}
    .ok {{ color: #16803c; }} .failed {{ color: #c62828; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ border-collapse: collapse; font-family: ui-monospace, monospace; font-size: 13px; width: max-content; min-width: 100%; }}
    th, td {{ border: 1px solid #8888; padding: 6px 9px; text-align: left; vertical-align: top; white-space: pre-wrap; word-break: break-word; }}
    th {{ position: sticky; top: 0; background: Canvas; }}
    pre {{ border: 1px solid #8888; overflow-x: auto; padding: 12px; white-space: pre-wrap; }}
    details {{ margin: 12px 0; }}
  </style>
</head>
<body>
  <h1>Oracle script test report</h1>
  <p>Generated {escape(generated_at)}</p>
  <div class="summary"><strong>{len(entries)} scripts</strong><span>{successful} succeeded</span><span>{failed} failed</span></div>
  {sections}
</body>
</html>
"""


def _render_entry(entry: ScriptReportEntry) -> str:
    """Render HTML markup for a single script report entry.

    Args:
        entry (ScriptReportEntry): Script execution record.

    Returns:
        str: HTML section markup for the entry.
    """
    status = "Succeeded" if entry.result is not None else "Failed"
    status_class = "ok" if entry.result is not None else "failed"
    body = f'<pre class="failed">{escape(entry.error or "Unknown error")}</pre>'
    if entry.result is not None:
        body = _render_result(entry.result)
    return f"""<section class="script">
  <h2>{escape(entry.script_name)} <small class="{status_class}">{status}</small></h2>
  <p>{escape(entry.test_name)}</p>
  {body}
</section>
"""


def _render_result(result: ScriptResult) -> str:
    """Render HTML markup for an executed script outcome.

    Args:
        result (ScriptResult): Outcome of script execution.

    Returns:
        str: HTML markup showing executed SQL, queries, and DBMS output.
    """
    statements = "\n\n".join(result.statements)
    query_sections = "".join(_render_query(index, query.columns, query.rows) for index, query in enumerate(result.queries, 1))
    if not query_sections:
        query_sections = "<p>No query result sets.</p>"
    output = "\n".join(result.dbms_output)
    output_section = f"<h3>DBMS output</h3><pre>{escape(output)}</pre>" if output else ""
    return f"""
  <details><summary>Executed SQL ({len(result.statements)} statements)</summary><pre>{escape(statements)}</pre></details>
  {query_sections}
  {output_section}
"""


def _render_query(index: int, columns: list[str], rows: list[tuple[object, ...]]) -> str:
    """Render HTML table for one query result set.

    Args:
        index (int): One-based result set index.
        columns (list[str]): Column headers.
        rows (list[tuple[object, ...]]): Data rows.

    Returns:
        str: HTML table markup.
    """
    headings = "".join(f"<th>{escape(column)}</th>" for column in columns)
    table_rows = "".join("<tr>" + "".join(f"<td>{escape(_display_value(value))}</td>" for value in row) + "</tr>" for row in rows)
    if not rows:
        table_rows = f'<tr><td colspan="{max(len(columns), 1)}"><em>No rows returned</em></td></tr>'
    return f"""<h3>Result set {index} ({len(rows)} rows)</h3>
  <div class="table-wrap"><table><thead><tr>{headings}</tr></thead><tbody>{table_rows}</tbody></table></div>
"""


def _display_value(value: object) -> str:
    """Format an arbitrary Python object as a display string.

    Args:
        value (object): Value to display.

    Returns:
        str: Formatted display string.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        return value.hex()
    return str(value)
