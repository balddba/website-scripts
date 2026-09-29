#!/usr/bin/env python3
# ===============================================================================
#
# Script Name: triggers.py
# Title: Report, enable, or disable Oracle triggers
# Tags: Python, Triggers, Schema, Administration
# Purpose: Report, enable, or disable selected Oracle triggers.
#
# Description:
#   Produces a detailed table trigger report with definitions and compilation
#   errors, or changes the state of matching triggers while continuing past
#   individual failures.
#
# Parameters:
#   action   - LIST, ENABLE, or DISABLE
#   target   - SCHEMA.% or SCHEMA.TABLE_NAME
#   category - ALL, BEFORE, AFTER, INSTEAD_OF, or COMPOUND
#   Command-line Oracle connection settings; use --help for details.
#
# Required Privileges:
#   - Read access to DBA_TRIGGERS, DBA_SOURCE, and DBA_ERRORS, or their ALL_ views
#   - Ownership of selected triggers or ALTER ANY TRIGGER for state changes
#
# Output Format:
#   - Plain-text trigger report or per-trigger action results
#
# Example Usage:
#   python triggers.py LIST HR.% ALL --service-name ORCLPDB1 --user system --password secret
#   python triggers.py DISABLE APP.ORDERS BEFORE --service-name ORCLPDB1 --user system --password secret
#
# Author: Aaron Myers <aaron@balddba.com>
#
# ===============================================================================
"""Report, enable, or disable Oracle table triggers."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import oracledb
import typer
from loguru import logger
from pydantic import BaseModel, Field, SecretStr

REPORT_WIDTH = 80
VALID_ACTIONS = ("LIST", "ENABLE", "DISABLE")
VALID_CATEGORIES = ("ALL", "BEFORE", "AFTER", "INSTEAD_OF", "COMPOUND")
IDENTIFIER_RE = re.compile(r"^[A-Z][A-Z0-9_$#]*$")


class OracleConnectionConfig(BaseModel):
    """Validated Oracle connection settings."""

    model_config = {"extra": "forbid"}

    hostname: str = Field(default="localhost")
    port: int = Field(default=1521, ge=1, le=65535)
    service_name: str | None = None
    sid: str | None = None
    username: str
    password: SecretStr
    is_sysdba: bool = False


@dataclass(frozen=True)
class Target:
    """A validated schema and table selection."""

    owner: str
    table_name: str


@dataclass
class TriggerError:
    """One trigger compilation error."""

    line: int
    position: int
    text: str


@dataclass
class TriggerInfo:
    """Catalog details for one trigger."""

    owner: str
    trigger_name: str
    table_name: str | None
    trigger_type: str
    triggering_event: str
    status: str
    when_clause: str | None
    source: str = ""
    errors: list[TriggerError] = field(default_factory=list)


@dataclass(frozen=True)
class ActionResult:
    """Result of an ENABLE or DISABLE operation."""

    statement: str
    succeeded: bool
    error: str | None = None


class ArgumentError(argparse.ArgumentTypeError, typer.BadParameter):
    """Exception for argument parsing errors, compatible with argparse and typer."""

    def __init__(self, message: str) -> None:
        """Initialize the argument error.

        Args:
            message (str): Error message.
        """
        argparse.ArgumentTypeError.__init__(self, message)
        typer.BadParameter.__init__(self, message)


def parse_target(value: str) -> Target:
    """Parse SCHEMA.% or SCHEMA.TABLE_NAME into a validated target.

    Args:
        value (str): Raw target string from command line.

    Returns:
        Target: Validated schema and table target.
    """
    normalized = value.strip().upper()
    if normalized.count(".") != 1:
        raise ArgumentError("target must be in SCHEMA.% or SCHEMA.TABLE_NAME format")
    owner, table_name = normalized.split(".", maxsplit=1)
    if not IDENTIFIER_RE.fullmatch(owner) or (table_name != "%" and not IDENTIFIER_RE.fullmatch(table_name)):
        raise ArgumentError("schema and table must be ordinary Oracle identifiers; only % is supported as a wildcard")
    return Target(owner=owner, table_name=table_name)


def normalize_action(value: str) -> str:
    """Normalize and validate an action argument.

    Args:
        value (str): Action name to validate.

    Returns:
        str: Normalized uppercase action name.
    """
    action = value.strip().upper()
    if action not in VALID_ACTIONS:
        raise ArgumentError(f"action must be one of: {', '.join(VALID_ACTIONS)}")
    return action


def normalize_category(value: str) -> str:
    """Normalize and validate a trigger timing category.

    Args:
        value (str): Category string from command line.

    Returns:
        str: Normalized trigger category name.
    """
    category = re.sub(r"[ -]+", "_", value.strip().upper())
    if category not in VALID_CATEGORIES:
        raise ArgumentError(f"category must be one of: {', '.join(VALID_CATEGORIES)}")
    return category


def quote_identifier(value: str) -> str:
    """Quote an identifier read from the Oracle data dictionary.

    Args:
        value (str): Raw Oracle identifier.

    Returns:
        str: Quoted identifier safe for SQL interpolation.
    """
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def build_alter_ddl(trigger: TriggerInfo, action: str) -> str:
    """Build a safely quoted ALTER TRIGGER statement.

    Args:
        trigger (TriggerInfo): Trigger metadata.
        action (str): DDL action verb (ENABLE or DISABLE).

    Returns:
        str: Complete ALTER TRIGGER DDL statement.
    """
    return f"ALTER TRIGGER {quote_identifier(trigger.owner)}.{quote_identifier(trigger.trigger_name)} {action}"


def format_trigger_ddl(trigger: TriggerInfo) -> str:
    """Render catalog source as executable CREATE OR REPLACE DDL.

    Args:
        trigger (TriggerInfo): Trigger metadata including source.

    Returns:
        str: Executable trigger DDL string.
    """
    source = trigger.source.strip().rstrip("/").rstrip()
    if not source:
        return "<definition unavailable>"
    if source.upper().startswith("CREATE "):
        ddl = source
    else:
        ddl = f"CREATE OR REPLACE {source}"
    return f"{ddl}\n/"


class OracleDriver:
    """Open Oracle database sessions."""

    def __init__(self, config: OracleConnectionConfig) -> None:
        """Initialize the driver with validated connection settings.

        Args:
            config (OracleConnectionConfig): Oracle connection settings and credentials.
        """
        self._config = config

    @contextmanager
    def session(self) -> Generator[oracledb.Connection, None, None]:
        """Yield an active Oracle connection.

        Yields:
            oracledb.Connection: Active Oracle database connection.
        """
        if self._config.service_name:
            dsn = oracledb.makedsn(self._config.hostname, self._config.port, service_name=self._config.service_name)
        elif self._config.sid:
            dsn = oracledb.makedsn(self._config.hostname, self._config.port, sid=self._config.sid)
        else:
            dsn = f"{self._config.hostname}:{self._config.port}"
        mode = oracledb.SYSDBA if self._config.is_sysdba or self._config.username.upper() == "SYS" else 0
        with oracledb.connect(
            user=self._config.username,
            password=self._config.password.get_secret_value(),
            dsn=dsn,
            mode=mode,
        ) as connection:
            yield connection


class TriggerRepository:
    """Read trigger metadata and apply state changes."""

    def __init__(self, connection: oracledb.Connection) -> None:
        """Initialize the repository with an active connection.

        Args:
            connection (oracledb.Connection): Active database connection.
        """
        self._connection = connection

    def database_name(self) -> str:
        """Return the current database name without requiring V$ privileges.

        Returns:
            str: Database name or unknown indicator.
        """
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT SYS_CONTEXT('USERENV', 'DB_NAME') FROM dual")
            row = cursor.fetchone()
        return str(row[0]) if row and row[0] is not None else "<unknown>"

    def fetch_triggers(self, target: Target, category: str) -> list[TriggerInfo]:
        """Fetch matching triggers, source, and compiler errors.

        Args:
            target (Target): Target schema and table criteria.
            category (str): Trigger timing category filter.

        Returns:
            list[TriggerInfo]: List of matching triggers with source and errors.
        """
        params = {"owner": target.owner, "table_name": target.table_name, "category": category}
        trigger_rows = self._query_with_fallback(self._trigger_sql("dba_triggers"), self._trigger_sql("all_triggers"), params)
        triggers = [
            TriggerInfo(
                owner=str(row[0]),
                trigger_name=str(row[1]),
                table_name=str(row[2]) if row[2] is not None else None,
                trigger_type=str(row[3]),
                triggering_event=str(row[4]),
                status=str(row[5]),
                when_clause=str(row[6]).strip() if row[6] is not None else None,
            )
            for row in trigger_rows
        ]
        if not triggers:
            return triggers

        names = {trigger.trigger_name for trigger in triggers}
        source_rows = self._query_with_fallback(self._source_sql("dba_source"), self._source_sql("all_source"), {"owner": target.owner})
        source_by_name: dict[str, list[str]] = {}
        for name, text in source_rows:
            if str(name) in names:
                source_by_name.setdefault(str(name), []).append(str(text))

        error_rows = self._query_with_fallback(self._error_sql("dba_errors"), self._error_sql("all_errors"), {"owner": target.owner})
        errors_by_name: dict[str, list[TriggerError]] = {}
        for name, line, position, text in error_rows:
            if str(name) in names:
                errors_by_name.setdefault(str(name), []).append(
                    TriggerError(
                        line=int(line or 0),
                        position=int(position or 0),
                        text=str(text).strip(),
                    )
                )

        for trigger in triggers:
            trigger.source = "".join(source_by_name.get(trigger.trigger_name, []))
            trigger.errors = errors_by_name.get(trigger.trigger_name, [])
        return triggers

    def change_state(self, triggers: Sequence[TriggerInfo], action: str) -> list[ActionResult]:
        """Change each trigger state, continuing after individual failures.

        Args:
            triggers (Sequence[TriggerInfo]): Triggers to alter.
            action (str): DDL action verb (ENABLE or DISABLE).

        Returns:
            list[ActionResult]: Execution result for each trigger.
        """
        results: list[ActionResult] = []
        with self._connection.cursor() as cursor:
            for trigger in triggers:
                statement = build_alter_ddl(trigger, action)
                try:
                    cursor.execute(statement)
                except oracledb.DatabaseError as exc:
                    results.append(ActionResult(statement=statement, succeeded=False, error=str(exc)))
                else:
                    results.append(ActionResult(statement=statement, succeeded=True))
        return results

    def _query_with_fallback(
        self,
        primary_sql: str,
        fallback_sql: str,
        params: dict[str, Any],
    ) -> list[tuple[Any, ...]]:
        """Use an ALL_ view when its DBA_ counterpart is unavailable.

        Args:
            primary_sql (str): Primary SQL query referencing DBA_ views.
            fallback_sql (str): Fallback SQL query referencing ALL_ views.
            params (dict[str, Any]): Dictionary of bind parameters.

        Returns:
            list[tuple[Any, ...]]: Fetched database rows.
        """
        with self._connection.cursor() as cursor:
            try:
                cursor.execute(primary_sql, params)
                return list(cursor.fetchall())
            except oracledb.DatabaseError as exc:
                error = exc.args[0] if exc.args else None
                if getattr(error, "code", 0) not in {942, 1031}:
                    raise
                logger.warning("DBA catalog view unavailable; falling back to ALL_ view")
                cursor.execute(fallback_sql, params)
                return list(cursor.fetchall())

    @staticmethod
    def _trigger_sql(view: str) -> str:
        """Generate trigger query SQL targeting the specified catalog view.

        Args:
            view (str): Triggers catalog view name.

        Returns:
            str: SQL query text.
        """
        return f"""
            SELECT owner, trigger_name, table_name, trigger_type,
                   triggering_event, status, when_clause
            FROM {view}
            WHERE owner = :owner
              AND (:table_name = '%' OR table_name = :table_name)
              AND (
                    :category = 'ALL'
                 OR (:category = 'BEFORE' AND trigger_type LIKE 'BEFORE%')
                 OR (:category = 'AFTER' AND trigger_type LIKE 'AFTER%')
                 OR (:category = 'INSTEAD_OF' AND trigger_type LIKE 'INSTEAD OF%')
                 OR (:category = 'COMPOUND' AND trigger_type = 'COMPOUND')
              )
            ORDER BY NVL(table_name, CHR(255)), trigger_name
        """

    @staticmethod
    def _source_sql(view: str) -> str:
        """Generate trigger source query SQL targeting the specified catalog view.

        Args:
            view (str): Source catalog view name.

        Returns:
            str: SQL query text.
        """
        return f"""
            SELECT name, text
            FROM {view}
            WHERE owner = :owner AND type = 'TRIGGER'
            ORDER BY name, line
        """

    @staticmethod
    def _error_sql(view: str) -> str:
        """Generate trigger error query SQL targeting the specified catalog view.

        Args:
            view (str): Errors catalog view name.

        Returns:
            str: SQL query text.
        """
        return f"""
            SELECT name, line, position, text
            FROM {view}
            WHERE owner = :owner AND type = 'TRIGGER'
            ORDER BY name, sequence
        """


def compact_trigger_type(trigger_type: str) -> str:
    """Shorten common table-trigger types for the summary.

    Args:
        trigger_type (str): Full trigger type description.

    Returns:
        str: Abbreviated trigger type text.
    """
    return trigger_type.upper().replace(" ROW", "")


def fit(value: str, width: int) -> str:
    """Truncate a value to a stable report column width.

    Args:
        value (str): Text value to fit within column.
        width (int): Maximum allowed column width.

    Returns:
        str: Truncated or formatted text.
    """
    return value if len(value) <= width else value[: width - 1] + "~"


def format_list_report(database_name: str, target: Target, triggers: Sequence[TriggerInfo], generated: datetime | None = None) -> str:
    """Format the detailed trigger report.

    Args:
        database_name (str): Current Oracle database name.
        target (Target): Target schema and table criteria.
        triggers (Sequence[TriggerInfo]): List of retrieved trigger records.
        generated (datetime | None): Optional timestamp of report generation.

    Returns:
        str: Multi-line formatted trigger report text.
    """
    generated = generated or datetime.now().astimezone()
    lines = [
        "=" * REPORT_WIDTH,
        " Oracle Table Trigger Report",
        "=" * REPORT_WIDTH,
        "",
        f"Database   : {database_name}",
        f"Schema     : {target.owner}",
        f"Table      : {target.table_name}",
        f"Generated  : {generated.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "-" * REPORT_WIDTH,
        " Trigger Summary",
        "-" * REPORT_WIDTH,
        "",
        f"{'Trigger Name':<30} {'Status':<9} {'Type':<13} {'Event':<26}".rstrip(),
        f"{'-' * 30} {'-' * 9} {'-' * 13} {'-' * 26}",
    ]
    for trigger in triggers:
        lines.append(f"{fit(trigger.trigger_name, 30):<30} {fit(trigger.status, 9):<9} {fit(compact_trigger_type(trigger.trigger_type), 13):<13} {fit(trigger.triggering_event, 26):<26}".rstrip())
    if not triggers:
        lines.append("No matching triggers found.")

    enabled = sum(trigger.status.upper() == "ENABLED" for trigger in triggers)
    disabled = sum(trigger.status.upper() == "DISABLED" for trigger in triggers)
    lines.extend(["", f"Triggers: {len(triggers)}", f"Enabled : {enabled}", f"Disabled: {disabled}"])

    for trigger in triggers:
        lines.extend(
            [
                "",
                "=" * REPORT_WIDTH,
                f" Trigger: {trigger.trigger_name}",
                "=" * REPORT_WIDTH,
                f"Status       : {trigger.status}",
                f"Owner        : {trigger.owner}",
                f"Table        : {trigger.table_name or '<schema/database>'}",
                f"Trigger Type : {trigger.trigger_type}",
                f"Event        : {trigger.triggering_event}",
                f"When Clause  : {trigger.when_clause or '<none>'}",
                "-" * REPORT_WIDTH,
                " Definition",
                "-" * REPORT_WIDTH,
                format_trigger_ddl(trigger),
            ]
        )

    errors = [(trigger.trigger_name, error) for trigger in triggers for error in trigger.errors]
    if errors:
        lines.extend(
            [
                "",
                "=" * REPORT_WIDTH,
                " Trigger Errors",
                "=" * REPORT_WIDTH,
                f"{'Trigger':<30} {'Line':>5} {'Pos':>4}  Error",
                f"{'-' * 30} {'-' * 5} {'-' * 4} {'-' * 39}",
            ]
        )
        for trigger_name, error in errors:
            lines.append(f"{fit(trigger_name, 30):<30} {error.line:>5} {error.position:>4}  {error.text}")

    lines.extend(["", "=" * REPORT_WIDTH, " End of Report", "=" * REPORT_WIDTH])
    return "\n".join(lines)


def format_action_report(action: str, target: Target, category: str, results: Sequence[ActionResult]) -> str:
    """Format ENABLE or DISABLE outcomes.

    Args:
        action (str): DDL action verb performed.
        target (Target): Target schema and table criteria.
        category (str): Timing category filter.
        results (Sequence[ActionResult]): List of action execution results.

    Returns:
        str: Formatted execution summary report text.
    """
    lines = [f"{action} triggers for {target.owner}.{target.table_name} (category: {category})", "-" * REPORT_WIDTH]
    for result in results:
        lines.append(result.statement + ";")
        lines.append("  OK" if result.succeeded else f"  ERROR: {result.error}")
    succeeded = sum(result.succeeded for result in results)
    lines.extend(
        [
            "-" * REPORT_WIDTH,
            f"Attempted: {len(results)}",
            f"Succeeded: {succeeded}",
            f"Failed:    {len(results) - succeeded}",
        ]
    )
    if not results:
        lines.append("No matching triggers required a status change.")
    return "\n".join(lines)


class TyperApp(typer.Typer):
    """Typer application with parse_args support for programmatic parsing."""

    def parse_args(self, args: Sequence[str] | None = None) -> SimpleNamespace:
        """Parse arguments into a namespace for programmatic use.

        Args:
            args (Sequence[str] | None): Argument list to parse.

        Returns:
            SimpleNamespace: Parsed arguments as a namespace.
        """
        cmd = typer.main.get_command(self)
        ctx = cmd.make_context("triggers", list(args) if args is not None else sys.argv[1:])
        ns = SimpleNamespace(**ctx.params)
        if hasattr(ns, "action"):
            ns.action = normalize_action(ns.action)
        if hasattr(ns, "target"):
            ns.target = parse_target(ns.target)
        if hasattr(ns, "category"):
            ns.category = normalize_category(ns.category)
        return ns


app = TyperApp(add_completion=False, help="Report, enable, or disable Oracle triggers.")


@app.command()
def run(
    action: str = typer.Argument(..., help="Action: LIST, ENABLE, or DISABLE"),
    target: str = typer.Argument(..., help="Target: SCHEMA.% or SCHEMA.TABLE_NAME"),
    category: str = typer.Argument(..., help="Category: ALL, BEFORE, AFTER, INSTEAD_OF, or COMPOUND"),
    host: str = typer.Option("localhost", "--host", envvar="ORACLE_HOST", help="Oracle database host"),
    port: int = typer.Option(1521, "--port", envvar="ORACLE_PORT", help="Oracle database port"),
    service_name: str | None = typer.Option(None, "--service-name", envvar="ORACLE_SERVICE_NAME", help="Oracle service name"),
    sid: str | None = typer.Option(None, "--sid", envvar="ORACLE_SID", help="Oracle SID"),
    user: str | None = typer.Option(None, "--user", envvar="ORACLE_USER", help="Database username"),
    password: str | None = typer.Option(None, "--password", envvar="ORACLE_PASSWORD", help="Database password"),
    sysdba: bool = typer.Option(False, "--sysdba", help="Connect with SYSDBA privilege"),
    output: str | None = typer.Option(None, "--output", help="Write output to this file instead of stdout"),
) -> int:
    """Run the trigger report or state change.

    Args:
        action (str): Action to perform.
        target (str): Target schema or table.
        category (str): Trigger category filter.
        host (str): Database hostname.
        port (int): Database port.
        service_name (str | None): Oracle service name.
        sid (str | None): Oracle SID.
        user (str | None): Database username.
        password (str | None): Database password.
        sysdba (bool): Connect with SYSDBA privilege.
        output (str | None): Output file path.

    Returns:
        int: Process exit code.
    """
    normalized_action = normalize_action(action)
    parsed_target = parse_target(target)
    normalized_cat = normalize_category(category)

    if not user or not password:
        logger.error("Database username and password are required via flags or ORACLE_USER/ORACLE_PASSWORD")
        return 1
    if not service_name and not sid:
        logger.error("Either --service-name or --sid is required")
        return 1

    config = OracleConnectionConfig(
        hostname=host,
        port=port,
        service_name=service_name,
        sid=sid,
        username=user,
        password=SecretStr(password),
        is_sysdba=sysdba,
    )
    try:
        with OracleDriver(config).session() as connection:
            repository = TriggerRepository(connection)
            triggers = repository.fetch_triggers(parsed_target, normalized_cat)
            if normalized_action == "LIST":
                report_output = format_list_report(repository.database_name(), parsed_target, triggers)
            else:
                desired_status = "DISABLED" if normalized_action == "ENABLE" else "ENABLED"
                selected = [trigger for trigger in triggers if trigger.status.upper() == desired_status]
                report_output = format_action_report(
                    normalized_action,
                    parsed_target,
                    normalized_cat,
                    repository.change_state(selected, normalized_action),
                )
    except oracledb.DatabaseError as exc:
        logger.error("Oracle operation failed: {}", exc)
        return 1

    if output:
        try:
            Path(output).write_text(report_output + "\n", encoding="utf-8")
        except OSError as exc:
            logger.error("Unable to write {}: {}", output, exc)
            return 1
    else:
        print(report_output)
    return 0


def build_parser() -> TyperApp:
    """Build the command-line parser.

    Returns:
        TyperApp: Configured Typer application.
    """
    return app


def main(argv: Sequence[str] | None = None) -> int:
    """Run the trigger report or state change entrypoint.

    Args:
        argv (Sequence[str] | None): Command-line arguments.

    Returns:
        int: Process exit code.
    """
    try:
        args = list(argv) if argv is not None else None
        ret = app(args=args, standalone_mode=False)
        return 0 if ret is None else int(ret)
    except typer.Exit as exc:
        return exc.exit_code
    except Exception as exc:
        logger.error("{}", exc)
        return 1


if __name__ == "__main__":
    app()
