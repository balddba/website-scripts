"""Shared assertions and per-script argument maps for catalog SQL tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import oracledb
import pytest

from tests.oracle.bootstrap import FixtureObjects
from tests.oracle.script_runner import ScriptResult
from tests.oracle.settings import OracleTestSettings

ArgsFactory = Callable[[FixtureObjects, OracleTestSettings], list[str]]
DefinesFactory = Callable[[FixtureObjects, OracleTestSettings], dict[str, str]]


@dataclass(frozen=True)
class ScriptSpec:
    """How to invoke one catalog SQL file under pytest.

    Attributes:
        args (list[str] | ArgsFactory): Positional SQL*Plus arguments.
        defines (dict[str, str] | DefinesFactory): Named SQL*Plus defines.
        skip_reason (str | None): Unconditional skip message.
        requires_instance_ddl (bool): Skip unless ORACLE_TEST_ALLOW_INSTANCE_DDL=1.
        requires_part_table (bool): Skip when the partitioned fixture table is absent.
        requires_xplan (bool): Skip when the XPLAN package is not installed.
        requires_tablespace (bool): Skip when the fixture table tablespace is unknown.
        expected_columns (set[str]): Columns that must occur together in one result set.
        expected_values (dict[str, str | Callable]): Fixture values required in the output.
        allow_no_output (bool): Permit DDL-only scripts verified by catalog side effects.
    """

    args: list[str] | ArgsFactory = field(default_factory=list)
    defines: dict[str, str] | DefinesFactory = field(default_factory=dict)
    skip_reason: str | None = None
    requires_instance_ddl: bool = False
    requires_part_table: bool = False
    requires_xplan: bool = False
    requires_tablespace: bool = False
    expected_columns: set[str] = field(default_factory=set)
    expected_values: dict[str, str | Callable[[FixtureObjects, OracleTestSettings], object]] = field(default_factory=dict)
    allow_no_output: bool = False


def _schema(_objects: FixtureObjects, _settings: OracleTestSettings) -> list[str]:
    return [_objects.schema]


def _schema_table(objects: FixtureObjects, _settings: OracleTestSettings) -> list[str]:
    return [objects.schema, objects.table]


def _owner_dot_table(objects: FixtureObjects, _settings: OracleTestSettings) -> list[str]:
    return [f"{objects.schema}.{objects.table}"]


def _user(_objects: FixtureObjects, settings: OracleTestSettings) -> list[str]:
    return [settings.user]


def _user_pair(_objects: FixtureObjects, settings: OracleTestSettings) -> list[str]:
    return [settings.user, settings.user]


SPECS: dict[str, ScriptSpec] = {
    "access.sql": ScriptSpec(args=_owner_dot_table),
    "aq_queue.sql": ScriptSpec(skip_reason="No disposable AQ queue is provisioned for tests"),
    "ash_pga_temp.sql": ScriptSpec(args=["30"]),
    "ash_top_sql.sql": ScriptSpec(args=["30"]),
    "ash_wait_chains.sql": ScriptSpec(args=["30"]),
    "block_change_tracking.sql": ScriptSpec(args=["STATUS"]),
    "compile.sql": ScriptSpec(args=_schema),
    "constraints.sql": ScriptSpec(args=lambda objects, _settings: ["LIST", f"{objects.schema}.{objects.table}", "ALL"]),
    "desc.sql": ScriptSpec(args=_owner_dot_table),
    "grant_tree.sql": ScriptSpec(args=_user),
    "histograms.sql": ScriptSpec(args=_schema_table),
    "index_stats.sql": ScriptSpec(
        args=_schema_table,
        expected_values={
            "OWNER": lambda objects, _settings: objects.schema,
            "TABLE_NAME": lambda objects, _settings: objects.table,
            "INDEX_NAME": lambda objects, _settings: objects.index,
        },
    ),
    "invalid_objects_summary.sql": ScriptSpec(),
    "io_distribution.sql": ScriptSpec(args=["FILE"]),
    "lob_space_usage.sql": ScriptSpec(args=_schema),
    "move_table_online.sql": ScriptSpec(
        args=lambda objects, _settings: [objects.schema, objects.table, objects.tablespace],
        requires_tablespace=True,
    ),
    "mview_log_orphans.sql": ScriptSpec(args=_schema),
    "mview_refresh_groups.sql": ScriptSpec(args=_schema),
    "mviews.sql": ScriptSpec(args=_schema),
    "object_ddl.sql": ScriptSpec(
        args=lambda objects, _settings: ["TABLE", objects.schema, objects.table],
        expected_columns={"DDL_TEXT"},
    ),
    "partitions.sql": ScriptSpec(
        args=lambda objects, _settings: [objects.schema, objects.part_table or "", "TABLE"],
        requires_part_table=True,
        expected_values={
            "OWNER": lambda objects, _settings: objects.schema,
            "OBJECT_NAME": lambda objects, _settings: objects.part_table,
        },
    ),
    "rebuild_indexes.sql": ScriptSpec(args=_schema_table),
    "rebuild_indexes_online.sql": ScriptSpec(
        args=lambda objects, _settings: [objects.schema, objects.table, objects.tablespace],
        requires_tablespace=True,
    ),
    "recyclebin_summary.sql": ScriptSpec(),
    "redundant_constraints.sql": ScriptSpec(args=_schema),
    "redundant_indexes.sql": ScriptSpec(args=_schema),
    "segment_space.sql": ScriptSpec(
        args=_schema_table,
        expected_values={
            "OWNER": lambda objects, _settings: objects.schema,
            "SEGMENT_NAME": lambda objects, _settings: objects.table,
        },
    ),
    "sequence.sql": ScriptSpec(
        args=lambda objects, _settings: [f"{objects.schema}.{objects.sequence}"],
        expected_values={
            "SEQUENCE_OWNER": lambda objects, _settings: objects.schema,
            "SEQUENCE_NAME": lambda objects, _settings: objects.sequence,
        },
    ),
    "sql_baselines.sql": ScriptSpec(args=["%"]),
    "sql_binds.sql": ScriptSpec(args=["%"]),
    "sql_history.sql": ScriptSpec(args=["%"]),
    "sql_monitor_report.sql": ScriptSpec(args=["%"]),
    "sql_patches_profiles.sql": ScriptSpec(args=["%"]),
    "table_clustering.sql": ScriptSpec(args=_owner_dot_table),
    "table_fragmentation.sql": ScriptSpec(args=_schema),
    "tables_without_pk.sql": ScriptSpec(args=_schema),
    "triggers.sql": ScriptSpec(args=lambda objects, _settings: ["LIST", f"{objects.schema}.{objects.table}", "ALL"]),
    "unstable_plans.sql": ScriptSpec(args=["VSQL"]),
    "user_details.sql": ScriptSpec(args=_user),
    "user_grant_copy.sql": ScriptSpec(
        defines=lambda _objects, settings: {"user1": settings.user, "user2": settings.user},
        requires_instance_ddl=True,
    ),
    "user_grant_sync.sql": ScriptSpec(
        defines=lambda _objects, settings: {"user1": settings.user, "user2": settings.user},
        requires_instance_ddl=True,
    ),
    "user_password_hash.sql": ScriptSpec(args=_user),
    "userdiff.sql": ScriptSpec(args=_user_pair),
    "xplan.display.sql": ScriptSpec(requires_xplan=True),
    "xplan.display_awr.sql": ScriptSpec(skip_reason="DISPLAY_AWR needs a captured SQL_ID and Diagnostic Pack"),
    "xplan.display_cursor.sql": ScriptSpec(requires_xplan=True),
    "xplan.package.sql": ScriptSpec(requires_instance_ddl=True, allow_no_output=True),
}


def run_catalog_script(
    run_oracle_sql: Callable[..., ScriptResult],
    objects: FixtureObjects,
    settings: OracleTestSettings,
    script_name: str,
) -> ScriptResult:
    """Run one catalog script with the mapped arguments and skip on missing views.

    Args:
        run_oracle_sql (Callable[..., ScriptResult]): Fixture that executes a script.
        objects (FixtureObjects): Bootstrap object names.
        settings (OracleTestSettings): Connection settings.
        script_name (str): File name under oracle/sql/.

    Returns:
        ScriptResult: Structured query output.

    Raises:
        oracledb.DatabaseError: If the script fails for a reason other than a missing view.
    """
    spec = SPECS.get(script_name, ScriptSpec())
    if spec.skip_reason:
        pytest.skip(spec.skip_reason)
    if spec.requires_instance_ddl and not settings.allow_instance_ddl:
        pytest.skip("ORACLE_TEST_ALLOW_INSTANCE_DDL is not enabled")
    if spec.requires_part_table and objects.part_table is None:
        pytest.skip("Partitioned fixture table was not created")
    if spec.requires_tablespace and not objects.tablespace:
        pytest.skip("Fixture table tablespace is unknown")
    if spec.requires_xplan and not objects.xplan_package:
        pytest.skip("XPLAN package is not installed")
    args = spec.args(objects, settings) if callable(spec.args) else list(spec.args)
    defines = spec.defines(objects, settings) if callable(spec.defines) else dict(spec.defines)
    try:
        result = run_oracle_sql(script_name, args=args, defines=defines)
    except oracledb.DatabaseError as exc:
        if _is_environment_limitation(exc):
            pytest.skip(str(exc).split("\n", maxsplit=1)[0])
        raise
    _assert_result_contract(result, objects, settings, script_name, spec)
    return result


def _assert_result_contract(
    result: ScriptResult,
    objects: FixtureObjects,
    settings: OracleTestSettings,
    script_name: str,
    spec: ScriptSpec,
) -> None:
    """Require observable output and any fixture-specific values for a script."""
    assert result.statements, f"{script_name} did not execute any SQL statements"
    assert spec.allow_no_output or result.queries or result.dbms_output, f"{script_name} produced no query or DBMS_OUTPUT results"
    for query in result.queries:
        assert query.columns, f"{script_name} returned a result set without columns"

    required_columns = set(spec.expected_columns) | set(spec.expected_values)
    if not required_columns:
        return
    matching = [query for query in result.queries if required_columns <= {column.upper() for column in query.columns}]
    assert matching, f"{script_name} did not return expected columns {sorted(required_columns)}"
    query = matching[0]
    expected_values: dict[str, object] = {}
    for column, raw_expected in spec.expected_values.items():
        expected_values[column] = raw_expected(objects, settings) if callable(raw_expected) else raw_expected
    indexes = {column: query.column_index(column) for column in expected_values}
    assert any(
        all(row[indexes[column]] == value for column, value in expected_values.items()) for row in query.rows
    ), f"{script_name} did not return expected row values {expected_values!r}"


def sid_values(result: ScriptResult, column: str = "SID") -> list[int]:
    """Collect integer SID-like values from every query in a result.

    Args:
        result (ScriptResult): Script execution result.
        column (str): Column name to read.

    Returns:
        list[int]: Values that could be converted to int.
    """
    found: list[int] = []
    for query in result.queries:
        try:
            values = query.values(column)
        except KeyError:
            continue
        for value in values:
            if value is None:
                continue
            found.append(int(value))
    return found


def _is_environment_limitation(exc: oracledb.DatabaseError) -> bool:
    """Return True when the test database lacks a required object or privilege.

    Args:
        exc (oracledb.DatabaseError): Driver exception from cursor.execute.

    Returns:
        bool: True if the test should skip rather than fail.
    """
    message = str(exc)
    return any(code in message for code in ("ORA-00942", "ORA-04043", "ORA-41900", "ORA-01031", "ORA-00439", "ORA-00904"))
