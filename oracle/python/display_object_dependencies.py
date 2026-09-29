#!/usr/bin/env python3
# ===============================================================================
#
# Script Name: display_object_dependencies.py
# Title: Display Oracle object dependencies
# Tags: Python, Dependencies, Metadata
# Purpose: Analyze and display dependency trees for Oracle database objects.
#
# Description:
#   Queries Oracle dependency metadata and renders direct or recursive object
#   dependency reports in text or structured output formats.
#
# Parameters:
#   Command-line Oracle connection settings and object filters; use --help.
#
# Required Privileges:
#   - Read access to the Oracle catalog views queried by the script
#
# Output Format:
#   - Dependency report written to standard output or the requested output file
#
# Example Usage:
#
# Author: Aaron Myers <aaron@balddba.com>
#
# ===============================================================================
"""Analyze and display object dependencies in Oracle database."""

from __future__ import annotations

import sys
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import oracledb
import typer
from loguru import logger
from pydantic import BaseModel, Field, SecretStr, ValidationError


class OracleConnectionConfig(BaseModel):
    """Configuration for connecting to an Oracle database.

    Attributes:
        hostname: Database host address or IP.
        port: Database listener port.
        service_name: Oracle service name.
        sid: Oracle System Identifier.
        username: Oracle database user.
        password: Secure password storage.
        is_sysdba: Whether to connect with SYSDBA privilege.
    """

    model_config = {"extra": "forbid"}

    hostname: str = Field(default="localhost", description="Database hostname")
    port: int = Field(default=1521, description="Database port")
    service_name: str | None = Field(default=None, description="Oracle service name")
    sid: str | None = Field(default=None, description="Oracle SID")
    username: str = Field(..., description="Database username")
    password: SecretStr = Field(..., description="Database password")
    is_sysdba: bool = Field(default=False, description="Connect with SYSDBA mode")


class DependencyItem(BaseModel):
    """Direct dependency record between two Oracle database objects.

    Attributes:
        owner: Schema owner of the dependent object.
        name: Name of the dependent object.
        object_type: Type of the dependent object.
        referenced_owner: Schema owner of the referenced object.
        referenced_name: Name of the referenced object.
        referenced_type: Type of the referenced object.
        referenced_link_name: Database link if referenced remotely.
        dependency_type: Dependency classification (e.g. HARD, REF).
    """

    model_config = {"extra": "forbid"}

    owner: str
    name: str
    object_type: str
    referenced_owner: str
    referenced_name: str
    referenced_type: str
    referenced_link_name: str | None = None
    dependency_type: str | None = None


class DependencyTreeNode(BaseModel):
    """Hierarchical node in an object dependency tree.

    Attributes:
        owner: Schema owner of the object.
        name: Name of the object.
        object_type: Type of object (TABLE, VIEW, PACKAGE, etc.).
        depth: Hierarchy depth level from root.
        is_cycle: Whether this node represents a circular dependency loop.
        children: Subordinate dependent or referenced nodes.
    """

    model_config = {"extra": "forbid"}

    owner: str
    name: str
    object_type: str
    depth: int = 0
    is_cycle: bool = False
    children: list[DependencyTreeNode] = Field(default_factory=list)


class ObjectDependencyReport(BaseModel):
    """Consolidated dependency analysis report.

    Attributes:
        generated_at: ISO 8601 generation timestamp.
        target_owner: Target schema owner analyzed.
        target_name: Target object name analyzed.
        target_type: Optional target object type.
        direction: Analysis direction (REFERENCES, DEPENDENTS, BOTH).
        max_depth: Maximum recursion depth configured.
        total_dependencies: Count of unique direct dependency relationships.
        references_tree: Tree of upstream objects that the target depends on.
        dependents_tree: Tree of downstream objects that depend on the target.
        direct_items: Flat list of direct dependencies.
    """

    model_config = {"extra": "forbid"}

    generated_at: str
    target_owner: str
    target_name: str
    target_type: str | None = None
    direction: str
    max_depth: int
    total_dependencies: int
    references_tree: DependencyTreeNode | None = None
    dependents_tree: DependencyTreeNode | None = None
    direct_items: list[DependencyItem] = Field(default_factory=list)


class OracleDriver:
    """Manages database connections to Oracle using python-oracledb Thin mode."""

    def __init__(self, config: OracleConnectionConfig) -> None:
        """Initialize driver with connection configuration.

        Args:
            config (OracleConnectionConfig): Validated database connection configuration.
        """
        self._config = config

    @contextmanager
    def session(self) -> Generator[oracledb.Connection, None, None]:
        """Context manager providing an active Oracle connection.

        Yields:
            oracledb.Connection: Active database connection.

        Raises:
            oracledb.DatabaseError: If connection cannot be established.
        """
        params: dict[str, Any] = {
            "user": self._config.username,
            "password": self._config.password.get_secret_value(),
            "host": self._config.hostname,
            "port": self._config.port,
        }
        if self._config.service_name:
            params["service_name"] = self._config.service_name
        elif self._config.sid:
            params["sid"] = self._config.sid
        else:
            params["service_name"] = "ORCLCDB"

        if self._config.is_sysdba:
            params["mode"] = oracledb.AUTH_MODE_SYSDBA

        logger.debug(
            "Connecting to Oracle host={} port={} sysdba={}",
            self._config.hostname,
            self._config.port,
            self._config.is_sysdba,
        )
        conn = oracledb.connect(**params)
        try:
            yield conn
        finally:
            conn.close()
            logger.debug("Oracle connection closed")


class ObjectDependencyAnalyzer:
    """Analyzes and reconstructs object dependency hierarchies in Oracle."""

    def __init__(self, driver: OracleDriver) -> None:
        """Initialize analyzer with an Oracle driver.

        Args:
            driver (OracleDriver): Oracle database connection driver.
        """
        self._driver = driver

    def query_references(
        self,
        owner: str,
        name: str,
        object_type: str | None = None,
    ) -> list[DependencyItem]:
        """Query upstream objects that the specified object directly depends on.

        Args:
            owner (str): Schema owner of the object.
            name (str): Object name.
            object_type (str | None): Optional object type filter.

        Returns:
            list[DependencyItem]: List of referenced dependency items.
        """
        clauses: list[str] = [
            "UPPER(owner) = UPPER(:owner)",
            "UPPER(name) = UPPER(:name)",
        ]
        binds: dict[str, Any] = {"owner": owner, "name": name}

        if object_type:
            clauses.append("UPPER(type) = UPPER(:obj_type)")
            binds["obj_type"] = object_type

        where_clause = " AND ".join(clauses)
        dba_query = f"""
            SELECT
                owner,
                name,
                type,
                referenced_owner,
                referenced_name,
                referenced_type,
                referenced_link_name,
                dependency_type
            FROM dba_dependencies
            WHERE {where_clause}
            ORDER BY referenced_owner, referenced_type, referenced_name
        """
        all_query = f"""
            SELECT
                owner,
                name,
                type,
                referenced_owner,
                referenced_name,
                referenced_type,
                referenced_link_name,
                dependency_type
            FROM all_dependencies
            WHERE {where_clause}
            ORDER BY referenced_owner, referenced_type, referenced_name
        """
        return self._execute_dependency_query(dba_query, all_query, binds)

    def query_dependents(
        self,
        owner: str,
        name: str,
        object_type: str | None = None,
    ) -> list[DependencyItem]:
        """Query downstream objects that directly depend on the specified object.

        Args:
            owner (str): Schema owner of the referenced object.
            name (str): Referenced object name.
            object_type (str | None): Optional referenced object type filter.

        Returns:
            list[DependencyItem]: List of dependent object items.
        """
        clauses: list[str] = [
            "UPPER(referenced_owner) = UPPER(:owner)",
            "UPPER(referenced_name) = UPPER(:name)",
        ]
        binds: dict[str, Any] = {"owner": owner, "name": name}

        if object_type:
            clauses.append("UPPER(referenced_type) = UPPER(:obj_type)")
            binds["obj_type"] = object_type

        where_clause = " AND ".join(clauses)
        dba_query = f"""
            SELECT
                owner,
                name,
                type,
                referenced_owner,
                referenced_name,
                referenced_type,
                referenced_link_name,
                dependency_type
            FROM dba_dependencies
            WHERE {where_clause}
            ORDER BY owner, type, name
        """
        all_query = f"""
            SELECT
                owner,
                name,
                type,
                referenced_owner,
                referenced_name,
                referenced_type,
                referenced_link_name,
                dependency_type
            FROM all_dependencies
            WHERE {where_clause}
            ORDER BY owner, type, name
        """
        return self._execute_dependency_query(dba_query, all_query, binds)

    def _execute_dependency_query(
        self,
        dba_query: str,
        all_query: str,
        binds: dict[str, Any],
    ) -> list[DependencyItem]:
        """Execute query against DBA_DEPENDENCIES with fallback to ALL_DEPENDENCIES.

        Args:
            dba_query (str): SQL query for DBA_DEPENDENCIES.
            all_query (str): Fallback SQL query for ALL_DEPENDENCIES.
            binds (dict[str, Any]): Named query bind parameters.

        Returns:
            list[DependencyItem]: Parsed dependency items.
        """
        with self._driver.session() as conn, conn.cursor() as cursor:
            rows: list[Any] = []
            try:
                cursor.execute(dba_query, binds)
                rows = cursor.fetchall()
            except oracledb.DatabaseError as exc:
                err = exc.args[0]
                if getattr(err, "code", None) == 942:
                    logger.warning("Access to DBA_DEPENDENCIES denied, falling back to ALL_DEPENDENCIES")
                    try:
                        cursor.execute(all_query, binds)
                        rows = cursor.fetchall()
                    except oracledb.DatabaseError as all_exc:
                        logger.error("Failed to query ALL_DEPENDENCIES: {}", all_exc)
                        return []
                else:
                    logger.error("Database error querying dependencies: {}", exc)
                    return []

            items: list[DependencyItem] = []
            for r in rows:
                items.append(
                    DependencyItem(
                        owner=str(r[0]),
                        name=str(r[1]),
                        object_type=str(r[2]),
                        referenced_owner=str(r[3]),
                        referenced_name=str(r[4]),
                        referenced_type=str(r[5]),
                        referenced_link_name=str(r[6]) if r[6] is not None else None,
                        dependency_type=str(r[7]) if r[7] is not None else None,
                    )
                )
            return items

    def build_dependency_tree(
        self,
        owner: str,
        name: str,
        object_type: str | None,
        direction: str = "references",
        max_depth: int = 5,
        current_depth: int = 0,
        visited_path: set[tuple[str, str, str]] | None = None,
    ) -> DependencyTreeNode:
        """Recursively build hierarchical dependency tree with cycle detection.

        Args:
            owner (str): Schema owner of root or intermediate node.
            name (str): Object name.
            object_type (str | None): Object type if known.
            direction (str): 'references' (upstream) or 'dependents' (downstream).
            max_depth (int): Maximum recursion depth.
            current_depth (int): Current recursion level.
            visited_path (set[tuple[str, str, str]] | None): Set of objects visited along current ancestry path.

        Returns:
            DependencyTreeNode: Populated tree node with children.
        """
        resolved_type = object_type or "OBJECT"
        node_key = (owner.upper(), name.upper(), resolved_type.upper())

        path_set = set(visited_path) if visited_path else set()
        if node_key in path_set:
            return DependencyTreeNode(
                owner=owner,
                name=name,
                object_type=resolved_type,
                depth=current_depth,
                is_cycle=True,
                children=[],
            )

        path_set.add(node_key)
        node = DependencyTreeNode(
            owner=owner,
            name=name,
            object_type=resolved_type,
            depth=current_depth,
            is_cycle=False,
            children=[],
        )

        if current_depth >= max_depth:
            return node

        if direction.lower() == "references":
            dep_items = self.query_references(owner, name, object_type)
            for item in dep_items:
                child_node = self.build_dependency_tree(
                    owner=item.referenced_owner,
                    name=item.referenced_name,
                    object_type=item.referenced_type,
                    direction=direction,
                    max_depth=max_depth,
                    current_depth=current_depth + 1,
                    visited_path=path_set,
                )
                node.children.append(child_node)
        else:
            dep_items = self.query_dependents(owner, name, object_type)
            for item in dep_items:
                child_node = self.build_dependency_tree(
                    owner=item.owner,
                    name=item.name,
                    object_type=item.object_type,
                    direction=direction,
                    max_depth=max_depth,
                    current_depth=current_depth + 1,
                    visited_path=path_set,
                )
                node.children.append(child_node)

        return node

    def analyze(
        self,
        owner: str,
        name: str,
        object_type: str | None = None,
        direction: str = "both",
        max_depth: int = 5,
    ) -> ObjectDependencyReport:
        """Run complete dependency analysis for specified object.

        Args:
            owner (str): Schema owner of the object.
            name (str): Name of the object.
            object_type (str | None): Optional object type filter.
            direction (str): Analysis direction ('references', 'dependents', or 'both').
            max_depth (int): Maximum recursion tree depth.

        Returns:
            ObjectDependencyReport: Comprehensive dependency report.
        """
        dir_norm = direction.lower()
        ref_tree: DependencyTreeNode | None = None
        dep_tree: DependencyTreeNode | None = None
        direct_items: list[DependencyItem] = []

        if dir_norm in ("references", "both"):
            ref_tree = self.build_dependency_tree(
                owner=owner,
                name=name,
                object_type=object_type,
                direction="references",
                max_depth=max_depth,
            )
            direct_items.extend(self.query_references(owner, name, object_type))

        if dir_norm in ("dependents", "both"):
            dep_tree = self.build_dependency_tree(
                owner=owner,
                name=name,
                object_type=object_type,
                direction="dependents",
                max_depth=max_depth,
            )
            direct_items.extend(self.query_dependents(owner, name, object_type))

        now_str = datetime.now(timezone.utc).isoformat()
        return ObjectDependencyReport(
            generated_at=now_str,
            target_owner=owner.upper(),
            target_name=name.upper(),
            target_type=object_type.upper() if object_type else None,
            direction=direction.upper(),
            max_depth=max_depth,
            total_dependencies=len(direct_items),
            references_tree=ref_tree,
            dependents_tree=dep_tree,
            direct_items=direct_items,
        )


def _render_tree_lines(
    node: DependencyTreeNode,
    prefix: str = "",
    is_last: bool = True,
    is_root: bool = True,
) -> list[str]:
    """Recursively render a tree node into indented ASCII lines.

    Args:
        node (DependencyTreeNode): Node to render.
        prefix (str): Indentation prefix for child lines.
        is_last (bool): Whether this node is the last child of its parent.
        is_root (bool): Whether this is the root node.

    Returns:
        list[str]: Formatted lines.
    """
    lines: list[str] = []
    cycle_marker = " [CIRCULAR DEPENDENCY]" if node.is_cycle else ""
    node_str = f"{node.owner}.{node.name} ({node.object_type}){cycle_marker}"

    if is_root:
        lines.append(node_str)
    else:
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{node_str}")

    if node.children:
        new_prefix = prefix + ("    " if is_last or is_root else "│   ")
        for i, child in enumerate(node.children):
            child_is_last = i == len(node.children) - 1
            lines.extend(
                _render_tree_lines(
                    child,
                    prefix=new_prefix,
                    is_last=child_is_last,
                    is_root=False,
                )
            )
    return lines


def format_dependency_text(report: ObjectDependencyReport) -> str:
    """Format dependency report into human-readable text.

    Args:
        report (ObjectDependencyReport): Populated object dependency report.

    Returns:
        str: Formatted report text.
    """
    out: list[str] = []
    out.append("================================================================================")
    out.append("                       Oracle Object Dependency Report                          ")
    out.append("================================================================================")
    out.append(f"Generated at: {report.generated_at}")
    target_str = f"{report.target_owner}.{report.target_name}"
    if report.target_type:
        target_str += f" ({report.target_type})"
    out.append(f"Target Object: {target_str}")
    out.append(f"Direction    : {report.direction}")
    out.append(f"Max Depth    : {report.max_depth}")
    out.append(f"Direct Dep Count: {report.total_dependencies}")
    out.append("--------------------------------------------------------------------------------\n")

    if report.references_tree:
        out.append("UPSTREAM DEPENDENCIES (Objects that this object references / depends on):")
        out.append("--------------------------------------------------------------------------------")
        if not report.references_tree.children:
            out.append(f"  {report.target_owner}.{report.target_name} has no upstream dependencies.")
        else:
            lines = _render_tree_lines(report.references_tree, is_root=True)
            for line in lines:
                out.append(f"  {line}")
        out.append("")

    if report.dependents_tree:
        out.append("DOWNSTREAM DEPENDENCIES (Objects that depend on this object):")
        out.append("--------------------------------------------------------------------------------")
        if not report.dependents_tree.children:
            out.append(f"  No dependent objects found that rely on {report.target_owner}.{report.target_name}.")
        else:
            lines = _render_tree_lines(report.dependents_tree, is_root=True)
            for line in lines:
                out.append(f"  {line}")
        out.append("")

    out.append("================================================================================")
    return "\n".join(out)


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
        ctx = cmd.make_context("display_object_dependencies", list(args) if args is not None else sys.argv[1:])
        return SimpleNamespace(**ctx.params)


app = TyperApp(add_completion=False, help="Display object dependency hierarchies in Oracle database.")


@app.command()
def run(
    name: str = typer.Option(..., "-n", "--name", help="Target object name (e.g. SCENES, GET_SCENE_INFO)"),
    user: str | None = typer.Option(None, "-u", "--user", envvar="ORACLE_USER", help="Oracle username"),
    password: str | None = typer.Option(None, "-p", "--password", envvar="ORACLE_PASSWORD", help="Oracle password"),
    host: str = typer.Option("localhost", "--host", envvar="ORACLE_HOST", help="Oracle host"),
    port: int = typer.Option(1521, "--port", envvar="ORACLE_PORT", help="Oracle listener port"),
    service_name: str | None = typer.Option(None, "--service-name", envvar="ORACLE_SERVICE_NAME", help="Oracle service name"),
    sid: str | None = typer.Option(None, "--sid", envvar="ORACLE_SID", help="Oracle SID"),
    sysdba: bool = typer.Option(False, "--sysdba", envvar="ORACLE_SYSDBA", help="Connect as SYSDBA"),
    owner: str | None = typer.Option(None, "-o", "--owner", help="Schema owner of target object (defaults to connected username)"),
    type: str | None = typer.Option(None, "-t", "--type", help="Target object type filter (e.g. TABLE, VIEW, PACKAGE, PACKAGE BODY)"),
    direction: str = typer.Option("both", "-d", "--direction", help="Dependency traversal direction (default: both)"),
    max_depth: int = typer.Option(5, "--max-depth", help="Maximum recursion depth for dependency tree (default: 5)"),
    format: str = typer.Option("text", "-f", "--format", help="Output format (default: text)"),
    output_file: str | None = typer.Option(None, "--output-file", help="Write report to file instead of stdout"),
) -> int:
    """Execute the object dependency analyzer CLI.

    Args:
        name (str): Target object name.
        user (str | None): Oracle username.
        password (str | None): Oracle password.
        host (str): Oracle host.
        port (int): Oracle listener port.
        service_name (str | None): Oracle service name.
        sid (str | None): Oracle SID.
        sysdba (bool): Connect as SYSDBA.
        owner (str | None): Schema owner.
        type (str | None): Target object type filter.
        direction (str): Dependency traversal direction.
        max_depth (int): Maximum recursion depth.
        format (str): Output format.
        output_file (str | None): Output file path.

    Returns:
        int: Exit status code.
    """
    if not user or not password:
        logger.error("Missing required credentials: username and password must be specified")
        return 1

    try:
        config = OracleConnectionConfig(
            hostname=host,
            port=port,
            service_name=service_name,
            sid=sid,
            username=user,
            password=SecretStr(password),
            is_sysdba=sysdba,
        )
    except ValidationError as err:
        logger.error("Configuration validation error: {}", err)
        return 1

    target_owner = owner or user
    driver = OracleDriver(config)
    analyzer = ObjectDependencyAnalyzer(driver)

    try:
        report = analyzer.analyze(
            owner=target_owner,
            name=name,
            object_type=type,
            direction=direction,
            max_depth=max_depth,
        )
    except (oracledb.DatabaseError, ValueError, RuntimeError, OSError) as exc:
        logger.error("Error executing object dependency analyzer: {}", exc)
        return 1

    if format == "json":
        output_text = report.model_dump_json(indent=2)
    else:
        output_text = format_dependency_text(report)

    if output_file:
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(output_text)
            logger.info("Report written to {}", output_file)
        except OSError as err:
            logger.error("Failed to write output to {}: {}", output_file, err)
            return 1
    else:
        sys.stdout.write(output_text + "\n")

    return 0


def parse_arguments(args: list[str]) -> SimpleNamespace:
    """Parse command-line arguments using Typer.

    Args:
        args (list[str]): Command line argument list.

    Returns:
        SimpleNamespace: Parsed CLI options.
    """
    return app.parse_args(args)


def main(args: list[str] | None = None) -> int:
    """Execute the object dependency analyzer CLI entrypoint.

    Args:
        args (list[str] | None): Optional list of CLI arguments (defaults to sys.argv[1:]).

    Returns:
        int: Exit status code (0 for success, non-zero for error).
    """
    try:
        cmd_args = list(args) if args is not None else None
        ret = app(args=cmd_args, standalone_mode=False)
        return 0 if ret is None else int(ret)
    except typer.Exit as exc:
        return exc.exit_code
    except Exception as exc:
        logger.error("{}", exc)
        return 1


if __name__ == "__main__":
    app()
