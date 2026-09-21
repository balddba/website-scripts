"""Execute parsed catalog SQL scripts through python-oracledb thin mode."""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import oracledb
from loguru import logger

from tests.oracle.script_parser import ParsedScript, apply_substitutions, parse_sqlplus_script
from tests.oracle.settings import OracleTestSettings

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = REPO_ROOT / "oracle" / "sql"
_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_#$]*$")
_BIND_NAME = re.compile(r":([A-Za-z][A-Za-z0-9_#$]*)")


@dataclass(frozen=True)
class QueryResult:
    """One SELECT result set from a catalog script.

    Attributes:
        columns (list[str]): Column names from the cursor description.
        rows (list[tuple[object, ...]]): Fetched rows.
    """

    columns: list[str]
    rows: list[tuple[object, ...]]

    def column_index(self, name: str) -> int:
        """Return the index of a column, matching case-insensitively.

        Args:
            name (str): Column name to find.

        Returns:
            int: Zero-based column index.

        Raises:
            KeyError: If the column is not in the result.
        """
        needle = name.upper()
        for index, column in enumerate(self.columns):
            if column.upper() == needle:
                return index
        raise KeyError(name)

    def values(self, name: str) -> list[object]:
        """Return every value in a named column.

        Args:
            name (str): Column name to collect.

        Returns:
            list[object]: Values from each row for that column.
        """
        index = self.column_index(name)
        return [row[index] for row in self.rows]


@dataclass
class ScriptResult:
    """Outcome of running a catalog SQL script.

    Attributes:
        statements (list[str]): Statements that were executed.
        queries (list[QueryResult]): SELECT result sets in execution order.
        dbms_output (list[str]): Lines collected from DBMS_OUTPUT.
    """

    statements: list[str]
    queries: list[QueryResult] = field(default_factory=list)
    dbms_output: list[str] = field(default_factory=list)


def quote_ident(name: str) -> str:
    """Return a validated unquoted Oracle identifier.

    Args:
        name (str): Identifier to validate.

    Returns:
        str: Upper-case identifier safe to interpolate into DDL.

    Raises:
        ValueError: If `name` is not a simple Oracle identifier.
    """
    if not _IDENT.match(name):
        raise ValueError(f"Invalid Oracle identifier: {name!r}")
    return name.upper()


@contextmanager
def oracle_connection(settings: OracleTestSettings) -> Iterator[oracledb.Connection]:
    """Open a thin-mode Oracle connection and close it when done.

    Args:
        settings (OracleTestSettings): Validated connection settings.

    Yields:
        oracledb.Connection: Open connection.

    Raises:
        oracledb.DatabaseError: If connect fails.
    """
    password = settings.password.get_secret_value()
    try:
        connection = oracledb.connect(user=settings.user, password=password, dsn=settings.connect)
    except oracledb.DatabaseError as exc:
        logger.bind(user=settings.user).error("oracle_connect_failed err={}", exc)
        raise
    try:
        yield connection
    finally:
        connection.close()


def run_script(
    connection: oracledb.Connection,
    script_name: str,
    args: list[str] | None = None,
    defines: dict[str, str] | None = None,
) -> ScriptResult:
    """Parse a catalog SQL file and execute its remaining statements.

    Args:
        connection (oracledb.Connection): Open Oracle session.
        script_name (str): File name under oracle/sql/.
        args (list[str] | None): Values for `&1`, `&2`, ...
        defines (dict[str, str] | None): Extra named SQL*Plus defines.

    Returns:
        ScriptResult: Query rows and DBMS_OUTPUT from the script.

    Raises:
        FileNotFoundError: If the catalog file is missing.
        oracledb.DatabaseError: If a statement fails.
    """
    path = SQL_DIR / script_name
    parsed = parse_sqlplus_script(path.read_text())
    return execute_parsed(
        connection,
        parsed,
        args=args or [],
        defines=defines or {},
    )


def execute_parsed(
    connection: oracledb.Connection,
    parsed: ParsedScript,
    args: list[str] | None = None,
    defines: dict[str, str] | None = None,
) -> ScriptResult:
    """Execute a parsed script on an open connection.

    Args:
        connection (oracledb.Connection): Open Oracle session.
        parsed (ParsedScript): Output of parse_sqlplus_script.
        args (list[str] | None): Values for `&1`, `&2`, ...
        defines (dict[str, str] | None): Extra named SQL*Plus defines.

    Returns:
        ScriptResult: Query rows and DBMS_OUTPUT from the script.

    Raises:
        oracledb.DatabaseError: If a statement fails.
    """
    positional = args or []
    active_defines = {key.upper(): value for key, value in parsed.defines.items()}
    if defines:
        active_defines.update({key.upper(): value for key, value in defines.items()})

    with connection.cursor() as cursor:
        _enable_dbms_output(cursor)
        bind_vars = _make_bind_vars(cursor, parsed.variables)
        queries: list[QueryResult] = []
        executed: list[str] = []
        for statement in parsed.statements:
            sql = apply_substitutions(statement, positional, active_defines)
            executed.append(sql)
            bind_values = _binds_for_statement(sql, bind_vars)
            try:
                if bind_values:
                    cursor.execute(sql, bind_values)
                else:
                    cursor.execute(sql)
            except oracledb.DatabaseError as exc:
                logger.error("sql_execute_failed err={} sql={}", exc, sql[:500])
                raise
            if cursor.description:
                columns = [item[0] for item in cursor.description]
                rows = [tuple(_materialize_value(value) for value in row) for row in cursor.fetchall()]
                queries.append(QueryResult(columns=columns, rows=rows))
                _capture_new_values(parsed.new_values, columns, rows, active_defines)
        output_lines = _read_dbms_output(cursor)
    return ScriptResult(statements=executed, queries=queries, dbms_output=output_lines)


def _materialize_value(value: object) -> object:
    """Read connection-bound Oracle values before their session closes."""
    read = getattr(value, "read", None)
    return read() if callable(read) else value


def _make_bind_vars(cursor: oracledb.Cursor, variables: dict[str, str]) -> dict[str, oracledb.Var]:
    """Allocate cursor variables for SQL*Plus VARIABLE declarations.

    Args:
        cursor (oracledb.Cursor): Cursor that owns the bind variables.
        variables (dict[str, str]): Bind name to VARIABLE type text.

    Returns:
        dict[str, oracledb.Var]: Bind name (original case from SQL is upper) to var.
    """
    binds: dict[str, oracledb.Var] = {}
    for name, type_text in variables.items():
        oracle_type = _oracle_type(type_text)
        if oracle_type == oracledb.DB_TYPE_VARCHAR:
            binds[name] = cursor.var(oracle_type, 4000)
        else:
            binds[name] = cursor.var(oracle_type)
    return binds


def _oracle_type(type_text: str) -> object:
    """Map a SQL*Plus VARIABLE type to an oracledb database type.

    Args:
        type_text (str): Type fragment such as NUMBER or VARCHAR2(128).

    Returns:
        object: oracledb DB_TYPE_* constant.
    """
    upper = type_text.upper()
    if upper.startswith(("NUMBER", "INTEGER", "BINARY_INTEGER", "PLS_INTEGER")):
        return oracledb.DB_TYPE_NUMBER
    return oracledb.DB_TYPE_VARCHAR


def _binds_for_statement(sql: str, bind_vars: dict[str, oracledb.Var]) -> dict[str, oracledb.Var]:
    """Return the subset of bind variables referenced in a statement.

    Args:
        sql (str): Statement text after substitution.
        bind_vars (dict[str, oracledb.Var]): All VARIABLE binds for the script.

    Returns:
        dict[str, oracledb.Var]: Binds that appear in `sql`.
    """
    used: dict[str, oracledb.Var] = {}
    for match in _BIND_NAME.finditer(sql):
        name = match.group(1).upper()
        if name in bind_vars:
            used[name] = bind_vars[name]
    return used


def _capture_new_values(
    new_values: dict[str, str],
    columns: list[str],
    rows: list[tuple[object, ...]],
    defines: dict[str, str],
) -> None:
    """Copy COLUMN NEW_VALUE aliases from a query into the define map.

    Args:
        new_values (dict[str, str]): Alias (upper) to define name.
        columns (list[str]): Result column names.
        rows (list[tuple[object, ...]]): Fetched rows.
        defines (dict[str, str]): Define map to update in place.
    """
    if not rows:
        return
    upper_columns = [column.upper() for column in columns]
    for alias, define_name in new_values.items():
        if alias in upper_columns:
            value = rows[0][upper_columns.index(alias)]
            defines[define_name.upper()] = "" if value is None else str(value)


def _enable_dbms_output(cursor: oracledb.Cursor) -> None:
    """Enable DBMS_OUTPUT collection for the session.

    Args:
        cursor (oracledb.Cursor): Open cursor.

    Raises:
        oracledb.DatabaseError: If ENABLE fails.
    """
    try:
        cursor.callproc("dbms_output.enable", [None])
    except oracledb.DatabaseError as exc:
        logger.error("dbms_output_enable_failed err={}", exc)
        raise


def _read_dbms_output(cursor: oracledb.Cursor) -> list[str]:
    """Drain DBMS_OUTPUT lines from the session.

    Args:
        cursor (oracledb.Cursor): Open cursor.

    Returns:
        list[str]: Output lines in order.

    Raises:
        oracledb.DatabaseError: If GET_LINES fails.
    """
    lines: list[str] = []
    chunk_size = 1000
    try:
        while True:
            line_array = cursor.arrayvar(oracledb.DB_TYPE_VARCHAR, chunk_size, 32767)
            num_var = cursor.var(oracledb.DB_TYPE_NUMBER)
            num_var.setvalue(0, chunk_size)
            cursor.callproc("dbms_output.get_lines", [line_array, num_var])
            count = int(num_var.getvalue() or 0)
            if count <= 0:
                break
            fetched = line_array.getvalue()
            lines.extend(str(item) for item in fetched[:count] if item is not None)
            if count < chunk_size:
                break
    except oracledb.DatabaseError as exc:
        logger.error("dbms_output_get_lines_failed err={}", exc)
        raise
    return lines
