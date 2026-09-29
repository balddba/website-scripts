"""Unit tests for the Oracle trigger report and state-change tool."""

from __future__ import annotations

import argparse
from datetime import datetime
from unittest.mock import MagicMock

import oracledb
import pytest

from oracle.python.triggers import (
    ActionResult,
    Target,
    TriggerError,
    TriggerInfo,
    TriggerRepository,
    build_alter_ddl,
    format_action_report,
    format_list_report,
    format_trigger_ddl,
    normalize_category,
    parse_target,
)


def trigger(**overrides) -> TriggerInfo:
    """Build a representative trigger for tests."""
    values = {
        "owner": "MVADMIN",
        "trigger_name": "TRG_ORDERS_BI",
        "table_name": "ORDERS",
        "trigger_type": "BEFORE EACH ROW",
        "triggering_event": "INSERT",
        "status": "ENABLED",
        "when_clause": None,
        "source": "TRIGGER MVADMIN.TRG_ORDERS_BI\nBEFORE INSERT ON MVADMIN.ORDERS\nBEGIN\n  NULL;\nEND;\n",
    }
    values.update(overrides)
    return TriggerInfo(**values)


def test_parse_target_normalizes_identifiers() -> None:
    """Target parsing should uppercase valid schema and table names."""
    assert parse_target("mvaDmin.orders") == Target("MVADMIN", "ORDERS")
    assert parse_target("MVADMIN.%") == Target("MVADMIN", "%")


@pytest.mark.parametrize("value", ["ORDERS", ".ORDERS", "APP.", "APP.ORDERS.EXTRA", "APP.ORD%"])
def test_parse_target_rejects_invalid_values(value: str) -> None:
    """Target parsing should reject malformed names and partial wildcards."""
    with pytest.raises(argparse.ArgumentTypeError, match=r"target|identifier|wildcard"):
        parse_target(value)


def test_normalize_category_accepts_readable_instead_of() -> None:
    """Category parsing should accept case and separator variants."""
    assert normalize_category("instead of") == "INSTEAD_OF"
    assert normalize_category("before") == "BEFORE"
    with pytest.raises(argparse.ArgumentTypeError, match="category"):
        normalize_category("DURING")


def test_ddl_generation_quotes_names_and_formats_source() -> None:
    """DDL helpers should quote identifiers and produce executable source."""
    item = trigger(owner='Odd"Owner', trigger_name='Trig"Name')
    assert build_alter_ddl(item, "ENABLE") == 'ALTER TRIGGER "Odd""Owner"."Trig""Name" ENABLE'
    ddl = format_trigger_ddl(item)
    assert ddl.startswith("CREATE OR REPLACE TRIGGER MVADMIN.TRG_ORDERS_BI")
    assert ddl.endswith("\n/")


def test_list_report_contains_requested_sections_counts_and_definition() -> None:
    """LIST output should contain the requested report sections and totals."""
    items = [
        trigger(),
        trigger(
            trigger_name="TRG_ORDERS_AUDIT",
            trigger_type="AFTER EACH ROW",
            triggering_event="INSERT OR UPDATE OR DELETE",
            status="DISABLED",
            when_clause="NEW.STATUS = 'CLOSED'",
        ),
    ]
    report = format_list_report("ORDERPROD", Target("MVADMIN", "ORDERS"), items, datetime(2026, 9, 28, 16, 31, 22))

    assert report.splitlines()[0] == "=" * 80
    assert " Oracle Table Trigger Report" in report
    assert "Database   : ORDERPROD" in report
    assert "Schema     : MVADMIN" in report
    assert "Table      : ORDERS" in report
    assert "Generated  : 2026-09-28 16:31:22" in report
    assert " Trigger Summary" in report
    assert "Triggers: 2" in report
    assert "Enabled : 1" in report
    assert "Disabled: 1" in report
    assert " Trigger: TRG_ORDERS_BI" in report
    assert "When Clause  : <none>" in report
    assert "CREATE OR REPLACE TRIGGER MVADMIN.TRG_ORDERS_BI" in report
    assert " End of Report" in report


def test_empty_list_report_is_explicit() -> None:
    """An empty LIST report should state that no triggers matched."""
    report = format_list_report("ORDERPROD", Target("MVADMIN", "%"), [], datetime(2026, 9, 28))
    assert "No matching triggers found." in report
    assert "Triggers: 0" in report
    assert " Trigger Errors" not in report


def test_list_report_includes_errors_only_when_present() -> None:
    """Compiler errors should appear in a dedicated optional section."""
    item = trigger(errors=[TriggerError(12, 7, "PLS-00201: identifier must be declared")])
    report = format_list_report("ORDERPROD", Target("MVADMIN", "ORDERS"), [item], datetime(2026, 9, 28))
    assert " Trigger Errors" in report
    assert "TRG_ORDERS_BI" in report
    assert "   12" in report
    assert "PLS-00201: identifier must be declared" in report


def test_fetch_triggers_falls_back_from_dba_to_all_views() -> None:
    """Catalog reads should fall back to ALL_ views after ORA-00942."""
    connection = MagicMock(spec=oracledb.Connection)
    cursor = MagicMock(spec=oracledb.Cursor)
    connection.cursor.return_value.__enter__.return_value = cursor
    error = oracledb.DatabaseError()
    error_object = MagicMock(code=942)
    error.args = (error_object,)
    cursor.execute.side_effect = [error, None, error, None, error, None]
    cursor.fetchall.side_effect = [
        [("MVADMIN", "TRG_ORDERS_BI", "ORDERS", "BEFORE EACH ROW", "INSERT", "ENABLED", None)],
        [("TRG_ORDERS_BI", "TRIGGER MVADMIN.TRG_ORDERS_BI\n"), ("TRG_ORDERS_BI", "BEGIN NULL; END;\n")],
        [("TRG_ORDERS_BI", 2, 3, "PLS-00000: test error")],
    ]

    items = TriggerRepository(connection).fetch_triggers(Target("MVADMIN", "ORDERS"), "ALL")

    assert len(items) == 1
    assert items[0].source.endswith("BEGIN NULL; END;\n")
    assert items[0].errors[0].line == 2
    executed_sql = [call.args[0].lower() for call in cursor.execute.call_args_list]
    assert any("all_triggers" in sql for sql in executed_sql)
    assert any("all_source" in sql for sql in executed_sql)
    assert any("all_errors" in sql for sql in executed_sql)


def test_change_state_continues_after_individual_failure() -> None:
    """State changes should continue and count outcomes after one failure."""
    connection = MagicMock(spec=oracledb.Connection)
    cursor = MagicMock(spec=oracledb.Cursor)
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.execute.side_effect = [oracledb.DatabaseError("ORA-01031"), None]

    results = TriggerRepository(connection).change_state([trigger(trigger_name="TRG_ONE"), trigger(trigger_name="TRG_TWO")], "DISABLE")

    assert [result.succeeded for result in results] == [False, True]
    report = format_action_report("DISABLE", Target("MVADMIN", "ORDERS"), "ALL", results)
    assert "Attempted: 2" in report
    assert "Succeeded: 1" in report
    assert "Failed:    1" in report
    assert "ORA-01031" in report


def test_action_report_handles_no_required_changes() -> None:
    """Action output should explain when every trigger already has the state."""
    report = format_action_report("ENABLE", Target("MVADMIN", "ORDERS"), "ALL", [])
    assert "Attempted: 0" in report
    assert "No matching triggers required a status change." in report


def test_action_result_representation() -> None:
    """Successful action results should not carry an error."""
    result = ActionResult('ALTER TRIGGER "APP"."T" ENABLE', True)
    assert result.error is None
