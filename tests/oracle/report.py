"""Render complete Oracle script results as a self-contained HTML report."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from tests.oracle.script_runner import ScriptResult


@dataclass(frozen=True)
class ScriptReportEntry:
    """One attempted catalog-script execution."""

    script_name: str
    test_name: str
    result: ScriptResult | None = None
    error: str | None = None


class OracleScriptReporter:
    """Collect script executions and write their complete results at session end."""

    def __init__(self, output_path: Path) -> None:
        """Create a reporter targeting ``output_path``."""
        self.output_path = output_path
        self.entries: list[ScriptReportEntry] = []

    def record_success(self, script_name: str, test_name: str, result: ScriptResult) -> None:
        """Record a successful script execution."""
        self.entries.append(ScriptReportEntry(script_name=script_name, test_name=test_name, result=result))

    def record_error(self, script_name: str, test_name: str, error: BaseException) -> None:
        """Record a script execution that raised an exception."""
        self.entries.append(ScriptReportEntry(script_name=script_name, test_name=test_name, error=str(error)))

    def write(self) -> Path:
        """Write the report, including when no scripts were attempted."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(render_html(self.entries), encoding="utf-8")
        return self.output_path


def render_html(entries: list[ScriptReportEntry]) -> str:
    """Return a self-contained HTML report for ``entries``."""
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
    headings = "".join(f"<th>{escape(column)}</th>" for column in columns)
    table_rows = "".join(
        "<tr>" + "".join(f"<td>{escape(_display_value(value))}</td>" for value in row) + "</tr>" for row in rows
    )
    if not rows:
        table_rows = f'<tr><td colspan="{max(len(columns), 1)}"><em>No rows returned</em></td></tr>'
    return f"""<h3>Result set {index} ({len(rows)} rows)</h3>
  <div class="table-wrap"><table><thead><tr>{headings}</tr></thead><tbody>{table_rows}</tbody></table></div>
"""


def _display_value(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        return value.hex()
    return str(value)
