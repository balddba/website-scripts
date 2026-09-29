"""Unit tests for the Oracle constraint report and state-change tool."""

from __future__ import annotations

import argparse
from datetime import datetime
from unittest.mock import MagicMock

import oracledb
import pytest

from oracle.python.constraints import (
    ActionResult,
    ConstraintInfo,
    ConstraintRepository,
    Target,
    build_alter_ddl,
    format_action_report,
    format_list_report,
    normalize_constraint_type,
    parse_target,
)


def constraint(**overrides) -> ConstraintInfo:
    """Build a representative constraint for tests."""
    values = {
        "owner": "MVADMIN",
        "table_name": "ORDERS",
        "constraint_name": "ORDERS_PK",
        "constraint_type": "P",
        "status": "ENABLED",
        "validated": "VALIDATED",
        "deferrable": "NOT DEFERRABLE",
        "deferred": "IMMEDIATE",
        "delete_rule": None,
        "search_condition": None,
        "referenced_owner": None,
        "referenced_table_name": None,
        "referenced_constraint_name": None,
        "columns": ["ORDER_ID"],
        "referenced_columns": [],
    }
    values.update(overrides)
    return ConstraintInfo(**values)


def test_parse_target_normalizes_identifiers() -> None:
    """Target parsing should uppercase valid schema and table names."""
    assert parse_target("mvaDmin.orders") == Target("MVADMIN", "ORDERS")
    assert parse_target("MVADMIN.%") == Target("MVADMIN", "%")


@pytest.mark.parametrize("value", ["ORDERS", ".ORDERS", "APP.", "APP.ORDERS.EXTRA", "APP.ORD%"])
def test_parse_target_rejects_invalid_values(value: str) -> None:
    """Target parsing should reject malformed names and partial wildcards."""
    with pytest.raises(argparse.ArgumentTypeError, match=r"target|identifier|wildcard"):
        parse_target(value)


def test_normalize_constraint_type_accepts_readable_names() -> None:
    """Constraint type parsing should accept case and separator variants."""
    assert normalize_constraint_type("primary key") == "P"
    assert normalize_constraint_type("foreign-key") == "R"
    assert normalize_constraint_type("all") is None
    with pytest.raises(argparse.ArgumentTypeError, match="constraint_type"):
        normalize_constraint_type("NOT_NULL")


def test_ddl_generation_quotes_table_and_constraint_names() -> None:
    """DDL helpers should quote identifiers from the catalog."""
    item = constraint(owner='Odd"Owner', table_name='Tab"Name', constraint_name='Con"Name')
    assert build_alter_ddl(item, "ENABLE") == 'ALTER TABLE "Odd""Owner"."Tab""Name" ENABLE CONSTRAINT "Con""Name"'


def test_list_report_contains_summary_details_and_condition() -> None:
    """LIST output should contain the requested report sections and details."""
    items = [
        constraint(),
        constraint(
            constraint_name="ORDERS_CUSTOMER_FK",
            constraint_type="R",
            delete_rule="CASCADE",
            referenced_owner="MVADMIN",
            referenced_table_name="CUSTOMERS",
            referenced_constraint_name="CUSTOMERS_PK",
            columns=["CUSTOMER_ID"],
            referenced_columns=["CUSTOMER_ID"],
        ),
        constraint(
            constraint_name="ORDERS_AMOUNT_CK",
            constraint_type="C",
            search_condition="AMOUNT >= 0",
            columns=["AMOUNT"],
            status="DISABLED",
        ),
    ]
    report = format_list_report("ORDERPROD", Target("MVADMIN", "ORDERS"), None, items, datetime(2026, 9, 28, 16, 31, 22))

    assert report.splitlines()[0] == "=" * 80
    assert " Oracle Table Constraint Report" in report
    assert "Database   : ORDERPROD" in report
    assert "Schema     : MVADMIN" in report
    assert "Table      : ORDERS" in report
    assert "Type       : ALL" in report
    assert "Generated  : 2026-09-28 16:31:22" in report
    assert " Constraint Summary" in report
    assert "Constraints: 3" in report
    assert "Enabled    : 2" in report
    assert "Disabled   : 1" in report
    assert " Constraint: ORDERS_PK" in report
    assert "Columns      : ORDER_ID" in report
    assert "References   : MVADMIN.CUSTOMERS.CUSTOMERS_PK" in report
    assert "Ref Columns  : CUSTOMER_ID" in report
    assert " Search Condition" in report
    assert "AMOUNT >= 0" in report
    assert " End of Report" in report


def test_empty_list_report_is_explicit() -> None:
    """An empty LIST report should state that no constraints matched."""
    report = format_list_report("ORDERPROD", Target("MVADMIN", "%"), "R", [], datetime(2026, 9, 28))
    assert "No matching constraints found." in report
    assert "Constraints: 0" in report
    assert "Type       : FOREIGN KEY" in report


def test_fetch_constraints_falls_back_from_dba_to_all_views() -> None:
    """Catalog reads should fall back to ALL_ views after ORA-00942."""
    connection = MagicMock(spec=oracledb.Connection)
    cursor = MagicMock(spec=oracledb.Cursor)
    connection.cursor.return_value.__enter__.return_value = cursor
    error = oracledb.DatabaseError()
    error_object = MagicMock(code=942)
    error.args = (error_object,)
    cursor.execute.side_effect = [error, None, error, None]
    cursor.fetchall.side_effect = [
        [
            (
                "MVADMIN",
                "ORDERS",
                "ORDERS_CUSTOMER_FK",
                "R",
                "ENABLED",
                "VALIDATED",
                "NOT DEFERRABLE",
                "IMMEDIATE",
                "CASCADE",
                None,
                "MVADMIN",
                "CUSTOMERS",
                "CUSTOMERS_PK",
            )
        ],
        [
            ("MVADMIN", "ORDERS_CUSTOMER_FK", "CUSTOMER_ID"),
            ("MVADMIN", "CUSTOMERS_PK", "CUSTOMER_ID"),
        ],
    ]

    items = ConstraintRepository(connection).fetch_constraints(Target("MVADMIN", "ORDERS"), "R")

    assert len(items) == 1
    assert items[0].columns == ["CUSTOMER_ID"]
    assert items[0].referenced_columns == ["CUSTOMER_ID"]
    executed_sql = [call.args[0].lower() for call in cursor.execute.call_args_list]
    assert any("all_constraints" in sql for sql in executed_sql)
    assert any("all_cons_columns" in sql for sql in executed_sql)


def test_change_state_continues_after_individual_failure() -> None:
    """State changes should continue and count outcomes after one failure."""
    connection = MagicMock(spec=oracledb.Connection)
    cursor = MagicMock(spec=oracledb.Cursor)
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.execute.side_effect = [oracledb.DatabaseError("ORA-02298"), None]

    results = ConstraintRepository(connection).change_state([constraint(constraint_name="FK_ONE"), constraint(constraint_name="FK_TWO")], "ENABLE")

    assert [result.succeeded for result in results] == [False, True]
    report = format_action_report("ENABLE", Target("MVADMIN", "ORDERS"), "R", results)
    assert "Attempted: 2" in report
    assert "Succeeded: 1" in report
    assert "Failed:    1" in report
    assert "ORA-02298" in report
    assert "referencing foreign key outside the requested scope" in report


def test_action_report_handles_no_required_changes() -> None:
    """Action output should explain when every constraint already has the state."""
    report = format_action_report("DISABLE", Target("MVADMIN", "ORDERS"), None, [])
    assert "Attempted: 0" in report
    assert "No matching constraints required a status change." in report


def test_action_result_representation() -> None:
    """Successful action results should not carry an error."""
    result = ActionResult('ALTER TABLE "APP"."T" ENABLE CONSTRAINT "T_PK"', True)
    assert result.error is None
