#!/usr/bin/env python3
# ===============================================================================
#
# Script Name: constraints.py
# Title: Report, enable, or disable Oracle constraints
# Tags: Python, Constraints, Schema, Administration
# Purpose: Report, enable, or disable selected Oracle table constraints.
#
# Description:
#   Produces a detailed table constraint report with constrained columns, search
#   conditions, and referenced keys, or changes the state of matching constraints
#   while continuing past individual failures.
#
# Parameters:
#   action          - LIST, ENABLE, or DISABLE
#   target          - SCHEMA.% or SCHEMA.TABLE_NAME
#   constraint_type - ALL, P, U, R, C, PRIMARY_KEY, UNIQUE, FOREIGN_KEY, or CHECK
#   Command-line Oracle connection settings; use --help for details.
#
# Required Privileges:
#   - Read access to DBA_CONSTRAINTS and DBA_CONS_COLUMNS, or their ALL_ views
#   - ALTER privilege on selected tables for state changes
#
# Output Format:
#   - Plain-text constraint report or per-constraint action results
#
# Example Usage:
#   python constraints.py LIST HR.% ALL --service-name ORCLPDB1 --user system --password secret
#   python constraints.py DISABLE APP.ORDERS FOREIGN_KEY --service-name ORCLPDB1 --user system --password secret
#
# Author: Aaron Myers <aaron@balddba.com>
#
# ===============================================================================
"""Report, enable, or disable Oracle table constraints."""

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
TYPE_ALIASES = {
    "ALL": None,
    "P": "P",
    "PRIMARY_KEY": "P",
    "PRIMARY KEY": "P",
    "U": "U",
    "UNIQUE": "U",
    "R": "R",
    "FOREIGN_KEY": "R",
    "FOREIGN KEY": "R",
    "C": "C",
    "CHECK": "C",
}
TYPE_LABELS = {"P": "PRIMARY KEY", "U": "UNIQUE", "R": "FOREIGN KEY", "C": "CHECK"}
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
class ConstraintInfo:
    """Catalog details for one table constraint."""

    owner: str
    table_name: str
    constraint_name: str
    constraint_type: str
    status: str
    validated: str
    deferrable: str
    deferred: str
    delete_rule: str | None
    search_condition: str | None
    referenced_owner: str | None
    referenced_table_name: str | None
    referenced_constraint_name: str | None
    columns: list[str] = field(default_factory=list)
    referenced_columns: list[str] = field(default_factory=list)


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


def normalize_constraint_type(value: str) -> str | None:
    """Normalize readable constraint type names to Oracle type codes.

    Args:
        value (str): Human-readable or shorthand constraint type.

    Returns:
        str | None: Oracle constraint type code or None for all.
    """
    constraint_type = re.sub(r"[ -]+", "_", value.strip().upper())
    if constraint_type not in TYPE_ALIASES:
        raise ArgumentError("constraint_type must be one of: ALL, P, U, R, C, PRIMARY_KEY, UNIQUE, FOREIGN_KEY, or CHECK")
    return TYPE_ALIASES[constraint_type]


def quote_identifier(value: str) -> str:
    """Quote an identifier read from the Oracle data dictionary.

    Args:
        value (str): Raw Oracle identifier.

    Returns:
        str: Quoted identifier safe for SQL interpolation.
    """
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def build_alter_ddl(constraint: ConstraintInfo, action: str) -> str:
    """Build a safely quoted ALTER TABLE statement.

    Args:
        constraint (ConstraintInfo): Constraint metadata.
        action (str): DDL action verb (ENABLE or DISABLE).

    Returns:
        str: Complete ALTER TABLE DDL statement.
    """
    return f"ALTER TABLE {quote_identifier(constraint.owner)}.{quote_identifier(constraint.table_name)} {action} CONSTRAINT {quote_identifier(constraint.constraint_name)}"


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


class ConstraintRepository:
    """Read constraint metadata and apply state changes."""

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

    def fetch_constraints(self, target: Target, constraint_type: str | None) -> list[ConstraintInfo]:
        """Fetch matching constraints and their constrained columns.

        Args:
            target (Target): Target schema and table criteria.
            constraint_type (str | None): Optional constraint type filter.

        Returns:
            list[ConstraintInfo]: Matching constraint details.
        """
        params = {"owner": target.owner, "table_name": target.table_name, "constraint_type": constraint_type}
        rows = self._query_with_fallback(
            self._constraint_sql("dba_constraints", "dba_constraints"),
            self._constraint_sql("all_constraints", "all_constraints"),
            params,
        )
        constraints = [
            ConstraintInfo(
                owner=str(row[0]),
                table_name=str(row[1]),
                constraint_name=str(row[2]),
                constraint_type=str(row[3]),
                status=str(row[4]),
                validated=str(row[5]),
                deferrable=str(row[6]),
                deferred=str(row[7]),
                delete_rule=str(row[8]) if row[8] is not None else None,
                search_condition=str(row[9]).strip() if row[9] is not None else None,
                referenced_owner=str(row[10]) if row[10] is not None else None,
                referenced_table_name=str(row[11]) if row[11] is not None else None,
                referenced_constraint_name=str(row[12]) if row[12] is not None else None,
            )
            for row in rows
        ]
        if not constraints:
            return constraints

        key_by_constraint = {(item.owner, item.constraint_name) for item in constraints}
        referenced_keys = {(item.referenced_owner, item.referenced_constraint_name) for item in constraints if item.referenced_owner and item.referenced_constraint_name}
        column_rows = self._query_with_fallback(
            self._column_sql("dba_cons_columns", "dba_constraints"),
            self._column_sql("all_cons_columns", "all_constraints"),
            {"owner": target.owner},
        )
        columns_by_key: dict[tuple[str, str], list[str]] = {}
        for owner, constraint_name, column_name in column_rows:
            key = (str(owner), str(constraint_name))
            if key in key_by_constraint or key in referenced_keys:
                columns_by_key.setdefault(key, []).append(str(column_name))

        for constraint in constraints:
            constraint.columns = columns_by_key.get((constraint.owner, constraint.constraint_name), [])
            if constraint.referenced_owner and constraint.referenced_constraint_name:
                constraint.referenced_columns = columns_by_key.get((constraint.referenced_owner, constraint.referenced_constraint_name), [])
        return constraints

    def change_state(self, constraints: Sequence[ConstraintInfo], action: str) -> list[ActionResult]:
        """Change each constraint state, continuing after individual failures.

        Args:
            constraints (Sequence[ConstraintInfo]): Constraints to alter.
            action (str): DDL action verb (ENABLE or DISABLE).

        Returns:
            list[ActionResult]: Execution result for each constraint.
        """
        results: list[ActionResult] = []
        with self._connection.cursor() as cursor:
            for constraint in constraints:
                statement = build_alter_ddl(constraint, action)
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
    def _constraint_sql(view: str, ref_view: str) -> str:
        """Generate constraint query SQL targeting the specified catalog view.

        Args:
            view (str): Constraints catalog view name.
            ref_view (str): Referenced constraints catalog view name.

        Returns:
            str: SQL query text.
        """
        return f"""
            SELECT c.owner, c.table_name, c.constraint_name, c.constraint_type,
                   c.status, c.validated, c.deferrable, c.deferred, c.delete_rule,
                   c.search_condition,
                   r.owner AS referenced_owner,
                   r.table_name AS referenced_table_name,
                   r.constraint_name AS referenced_constraint_name
            FROM {view} c
            LEFT JOIN {ref_view} r
              ON r.owner = c.r_owner
             AND r.constraint_name = c.r_constraint_name
            WHERE c.owner = :owner
              AND (:table_name = '%' OR c.table_name = :table_name)
              AND c.constraint_type IN ('P', 'U', 'R', 'C')
              AND (:constraint_type IS NULL OR c.constraint_type = :constraint_type)
            ORDER BY
                CASE
                    WHEN c.constraint_type IN ('P', 'U') THEN 10
                    WHEN c.constraint_type = 'C' THEN 20
                    WHEN c.constraint_type = 'R' THEN 30
                    ELSE 40
                END,
                c.table_name,
                c.constraint_name
        """

    @staticmethod
    def _column_sql(view: str, constraint_view: str) -> str:
        """Generate constraint column query SQL targeting the specified catalog view.

        Args:
            view (str): Constraint columns catalog view name.
            constraint_view (str): Constraints catalog view name.

        Returns:
            str: SQL query text.
        """
        return f"""
            SELECT owner, constraint_name, column_name
            FROM {view}
            WHERE owner = :owner
               OR (owner, constraint_name) IN (
                    SELECT r_owner, r_constraint_name
                    FROM {constraint_view}
                    WHERE owner = :owner
                      AND r_owner IS NOT NULL
                      AND r_constraint_name IS NOT NULL
               )
            ORDER BY owner, constraint_name, position
        """


def constraint_type_label(value: str) -> str:
    """Return a readable label for an Oracle constraint type code.

    Args:
        value (str): Single-letter Oracle constraint type code.

    Returns:
        str: Human-readable constraint type label.
    """
    return TYPE_LABELS.get(value.upper(), value)


def fit(value: str, width: int) -> str:
    """Truncate a value to a stable report column width.

    Args:
        value (str): Text value to fit within column.
        width (int): Maximum allowed column width.

    Returns:
        str: Truncated or formatted text.
    """
    return value if len(value) <= width else value[: width - 1] + "~"


def format_columns(columns: Sequence[str]) -> str:
    """Render a constraint column list.

    Args:
        columns (Sequence[str]): Ordered list of column names.

    Returns:
        str: Comma-separated list or unavailable indicator.
    """
    return ", ".join(columns) if columns else "<not available>"


def format_list_report(
    database_name: str,
    target: Target,
    constraint_type: str | None,
    constraints: Sequence[ConstraintInfo],
    generated: datetime | None = None,
) -> str:
    """Format the detailed constraint report.

    Args:
        database_name (str): Current Oracle database name.
        target (Target): Target schema and table criteria.
        constraint_type (str | None): Optional constraint type filter.
        constraints (Sequence[ConstraintInfo]): List of retrieved constraints.
        generated (datetime | None): Optional timestamp of report generation.

    Returns:
        str: Multi-line formatted constraint report text.
    """
    generated = generated or datetime.now().astimezone()
    requested_type = constraint_type_label(constraint_type) if constraint_type else "ALL"
    lines = [
        "=" * REPORT_WIDTH,
        " Oracle Table Constraint Report",
        "=" * REPORT_WIDTH,
        "",
        f"Database   : {database_name}",
        f"Schema     : {target.owner}",
        f"Table      : {target.table_name}",
        f"Type       : {requested_type}",
        f"Generated  : {generated.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "-" * REPORT_WIDTH,
        " Constraint Summary",
        "-" * REPORT_WIDTH,
        "",
        f"{'Table':<24} {'Constraint':<30} {'Type':<11} {'Status':<9}".rstrip(),
        f"{'-' * 24} {'-' * 30} {'-' * 11} {'-' * 9}",
    ]
    for constraint in constraints:
        lines.append(f"{fit(constraint.table_name, 24):<24} {fit(constraint.constraint_name, 30):<30} {fit(constraint_type_label(constraint.constraint_type), 11):<11} {fit(constraint.status, 9):<9}".rstrip())
    if not constraints:
        lines.append("No matching constraints found.")

    enabled = sum(constraint.status.upper() == "ENABLED" for constraint in constraints)
    disabled = sum(constraint.status.upper() == "DISABLED" for constraint in constraints)
    lines.extend(["", f"Constraints: {len(constraints)}", f"Enabled    : {enabled}", f"Disabled   : {disabled}"])

    for constraint in constraints:
        lines.extend(
            [
                "",
                "=" * REPORT_WIDTH,
                f" Constraint: {constraint.constraint_name}",
                "=" * REPORT_WIDTH,
                f"Status       : {constraint.status}",
                f"Owner        : {constraint.owner}",
                f"Table        : {constraint.table_name}",
                f"Type         : {constraint_type_label(constraint.constraint_type)}",
                f"Columns      : {format_columns(constraint.columns)}",
                f"Validated    : {constraint.validated}",
                f"Deferrable   : {constraint.deferrable}",
                f"Deferred     : {constraint.deferred}",
            ]
        )
        if constraint.constraint_type == "R":
            referenced = f"{constraint.referenced_owner}.{constraint.referenced_table_name}.{constraint.referenced_constraint_name}" if constraint.referenced_owner and constraint.referenced_table_name and constraint.referenced_constraint_name else "<not available>"
            lines.extend(
                [
                    f"Delete Rule  : {constraint.delete_rule or '<none>'}",
                    f"References   : {referenced}",
                    f"Ref Columns  : {format_columns(constraint.referenced_columns)}",
                ]
            )
        if constraint.constraint_type == "C":
            lines.extend(["-" * REPORT_WIDTH, " Search Condition", "-" * REPORT_WIDTH, constraint.search_condition or "<not available>"])

    lines.extend(["", "=" * REPORT_WIDTH, " End of Report", "=" * REPORT_WIDTH])
    return "\n".join(lines)


def format_action_report(action: str, target: Target, constraint_type: str | None, results: Sequence[ActionResult]) -> str:
    """Format ENABLE or DISABLE outcomes.

    Args:
        action (str): DDL action verb performed.
        target (Target): Target schema and table criteria.
        constraint_type (str | None): Optional constraint type filter.
        results (Sequence[ActionResult]): List of action execution results.

    Returns:
        str: Formatted execution summary report text.
    """
    requested_type = constraint_type_label(constraint_type) if constraint_type else "ALL"
    lines = [f"{action} constraints for {target.owner}.{target.table_name} (type: {requested_type})", "-" * REPORT_WIDTH]
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
        lines.append("No matching constraints required a status change.")
    if results and len(results) != succeeded:
        lines.append("Review failures above. A common cause is a referencing foreign key outside the requested scope.")
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
        ctx = cmd.make_context("constraints", list(args) if args is not None else sys.argv[1:])
        ns = SimpleNamespace(**ctx.params)
        if hasattr(ns, "action"):
            ns.action = normalize_action(ns.action)
        if hasattr(ns, "target"):
            ns.target = parse_target(ns.target)
        if hasattr(ns, "constraint_type"):
            ns.constraint_type = normalize_constraint_type(ns.constraint_type)
        return ns


app = TyperApp(add_completion=False, help="Report, enable, or disable Oracle constraints.")


@app.command()
def run(
    action: str = typer.Argument(..., help="Action: LIST, ENABLE, or DISABLE"),
    target: str = typer.Argument(..., help="Target: SCHEMA.% or SCHEMA.TABLE_NAME"),
    constraint_type: str = typer.Argument(..., help="Constraint type: ALL, P, U, R, C, etc."),
    host: str = typer.Option("localhost", "--host", envvar="ORACLE_HOST", help="Oracle database host"),
    port: int = typer.Option(1521, "--port", envvar="ORACLE_PORT", help="Oracle database port"),
    service_name: str | None = typer.Option(None, "--service-name", envvar="ORACLE_SERVICE_NAME", help="Oracle service name"),
    sid: str | None = typer.Option(None, "--sid", envvar="ORACLE_SID", help="Oracle SID"),
    user: str | None = typer.Option(None, "--user", envvar="ORACLE_USER", help="Database username"),
    password: str | None = typer.Option(None, "--password", envvar="ORACLE_PASSWORD", help="Database password"),
    sysdba: bool = typer.Option(False, "--sysdba", help="Connect with SYSDBA privilege"),
    output: str | None = typer.Option(None, "--output", help="Write output to this file instead of stdout"),
) -> int:
    """Run the constraint report or state change.

    Args:
        action (str): Action to perform.
        target (str): Target schema or table.
        constraint_type (str): Constraint type filter.
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
    normalized_type = normalize_constraint_type(constraint_type)

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
            repository = ConstraintRepository(connection)
            constraints = repository.fetch_constraints(parsed_target, normalized_type)
            if normalized_action == "LIST":
                report_output = format_list_report(repository.database_name(), parsed_target, normalized_type, constraints)
            else:
                desired_status = "DISABLED" if normalized_action == "ENABLE" else "ENABLED"
                selected = [constraint for constraint in constraints if constraint.status.upper() == desired_status]
                report_output = format_action_report(
                    normalized_action,
                    parsed_target,
                    normalized_type,
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
    """Run the constraint report or state change entrypoint.

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
