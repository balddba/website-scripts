"""Unit tests for Oracle object dependency analyzer script."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import oracledb
import pytest
from pydantic import SecretStr, ValidationError

from oracle.python.display_object_dependencies import (
    DependencyItem,
    DependencyTreeNode,
    ObjectDependencyAnalyzer,
    ObjectDependencyReport,
    OracleConnectionConfig,
    OracleDriver,
    format_dependency_text,
    main,
)


def test_oracle_connection_config_valid() -> None:
    """Test valid configuration instantiation."""
    config = OracleConnectionConfig(
        hostname="db.example.com",
        port=1521,
        service_name="ORCLPDB1",
        username="c##admin",
        password=SecretStr("supersecret"),
        is_sysdba=True,
    )
    assert config.hostname == "db.example.com"
    assert config.port == 1521
    assert config.service_name == "ORCLPDB1"
    assert config.username == "c##admin"
    assert config.password.get_secret_value() == "supersecret"
    assert config.is_sysdba is True


def test_oracle_connection_config_extra_forbidden() -> None:
    """Test that extra fields raise validation errors."""
    with pytest.raises(ValidationError):
        OracleConnectionConfig(
            username="user",
            password=SecretStr("pass"),
            unknown_attr="fail",  # type: ignore[call-arg]
        )


def test_oracle_connection_config_missing_required() -> None:
    """Test that missing required fields raise validation errors."""
    with pytest.raises(ValidationError):
        OracleConnectionConfig(username="user")  # type: ignore[call-arg]


def test_oracle_driver_session_connect() -> None:
    """Test driver session connection establishment and close."""
    config = OracleConnectionConfig(
        hostname="localhost",
        port=1521,
        service_name="XEPDB1",
        username="testuser",
        password=SecretStr("testpass"),
        is_sysdba=True,
    )
    driver = OracleDriver(config)
    mock_conn = MagicMock(spec=oracledb.Connection)

    with patch("oracledb.connect", return_value=mock_conn) as mock_connect:
        with driver.session() as conn:
            assert conn is mock_conn
        mock_connect.assert_called_once_with(
            user="testuser",
            password="testpass",
            host="localhost",
            port=1521,
            service_name="XEPDB1",
            mode=oracledb.AUTH_MODE_SYSDBA,
        )
        mock_conn.close.assert_called_once()


def test_oracle_driver_session_failure() -> None:
    """Test driver session handling connection error."""
    config = OracleConnectionConfig(
        hostname="localhost",
        port=1521,
        service_name="XEPDB1",
        username="testuser",
        password=SecretStr("wrongpass"),
    )
    driver = OracleDriver(config)
    with (
        patch("oracledb.connect", side_effect=oracledb.DatabaseError("ORA-01017")),
        pytest.raises(oracledb.DatabaseError),
        driver.session(),
    ):
        pass


def test_query_references_happy_path() -> None:
    """Test querying upstream references from DBA_DEPENDENCIES."""
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # owner, name, type, referenced_owner, referenced_name, referenced_type, referenced_link_name, dependency_type
    rows = [
        ("STASH", "GET_SCENE", "PROCEDURE", "STASH", "SCENES", "TABLE", None, "HARD"),
        ("STASH", "GET_SCENE", "PROCEDURE", "SYS", "STANDARD", "PACKAGE", None, "HARD"),
    ]
    mock_cursor.fetchall.return_value = rows

    mock_driver = MagicMock(spec=OracleDriver)
    mock_driver.session.return_value.__enter__.return_value = mock_conn

    analyzer = ObjectDependencyAnalyzer(mock_driver)
    items = analyzer.query_references(owner="STASH", name="GET_SCENE")

    assert len(items) == 2
    assert items[0].referenced_name == "SCENES"
    assert items[0].referenced_type == "TABLE"
    assert items[1].referenced_name == "STANDARD"


def test_query_dependents_happy_path() -> None:
    """Test querying downstream dependents from DBA_DEPENDENCIES."""
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    rows = [
        ("STASH", "SCENE_VIEW", "VIEW", "STASH", "SCENES", "TABLE", None, "HARD"),
        ("STASH", "SCENE_PKG", "PACKAGE BODY", "STASH", "SCENES", "TABLE", None, "REF"),
    ]
    mock_cursor.fetchall.return_value = rows

    mock_driver = MagicMock(spec=OracleDriver)
    mock_driver.session.return_value.__enter__.return_value = mock_conn

    analyzer = ObjectDependencyAnalyzer(mock_driver)
    items = analyzer.query_dependents(owner="STASH", name="SCENES")

    assert len(items) == 2
    assert items[0].name == "SCENE_VIEW"
    assert items[1].name == "SCENE_PKG"


def test_query_dependencies_fallback_on_ora_942() -> None:
    """Test query fallback to ALL_DEPENDENCIES when DBA_DEPENDENCIES is inaccessible."""
    mock_conn = MagicMock(spec=oracledb.Connection)
    mock_cursor = MagicMock(spec=oracledb.Cursor)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    ora_942 = oracledb.DatabaseError("ORA-00942: table or view does not exist")
    ora_942_obj = MagicMock()
    ora_942_obj.code = 942
    ora_942.args = (ora_942_obj,)

    all_rows = [
        ("STASH", "GET_SCENE", "PROCEDURE", "STASH", "SCENES", "TABLE", None, "HARD"),
    ]

    mock_cursor.execute.side_effect = [ora_942, None]
    mock_cursor.fetchall.return_value = all_rows

    mock_driver = MagicMock(spec=OracleDriver)
    mock_driver.session.return_value.__enter__.return_value = mock_conn

    analyzer = ObjectDependencyAnalyzer(mock_driver)
    items = analyzer.query_references(owner="STASH", name="GET_SCENE")

    assert len(items) == 1
    assert items[0].referenced_name == "SCENES"


def test_build_dependency_tree_with_cycle_detection() -> None:
    """Test recursive dependency tree building with cycle detection."""
    mock_driver = MagicMock(spec=OracleDriver)
    analyzer = ObjectDependencyAnalyzer(mock_driver)

    # Simulate circular dependency: VIEW_A -> VIEW_B -> VIEW_A
    def mock_references(owner: str, name: str, obj_type: str | None = None) -> list[DependencyItem]:
        if name.upper() == "VIEW_A":
            return [
                DependencyItem(
                    owner="STASH",
                    name="VIEW_A",
                    object_type="VIEW",
                    referenced_owner="STASH",
                    referenced_name="VIEW_B",
                    referenced_type="VIEW",
                )
            ]
        if name.upper() == "VIEW_B":
            return [
                DependencyItem(
                    owner="STASH",
                    name="VIEW_B",
                    object_type="VIEW",
                    referenced_owner="STASH",
                    referenced_name="VIEW_A",
                    referenced_type="VIEW",
                )
            ]
        return []

    with patch.object(analyzer, "query_references", side_effect=mock_references):
        tree = analyzer.build_dependency_tree(
            owner="STASH",
            name="VIEW_A",
            object_type="VIEW",
            direction="references",
            max_depth=5,
        )

    assert tree.name == "VIEW_A"
    assert len(tree.children) == 1
    child = tree.children[0]
    assert child.name == "VIEW_B"
    assert len(child.children) == 1
    grandchild = child.children[0]
    assert grandchild.name == "VIEW_A"
    assert grandchild.is_cycle is True
    assert len(grandchild.children) == 0


def test_analyze_consolidation() -> None:
    """Test consolidated dependency report generation."""
    mock_driver = MagicMock(spec=OracleDriver)
    analyzer = ObjectDependencyAnalyzer(mock_driver)

    ref_items = [
        DependencyItem(
            owner="STASH",
            name="MY_PKG",
            object_type="PACKAGE BODY",
            referenced_owner="STASH",
            referenced_name="SCENES",
            referenced_type="TABLE",
        )
    ]
    dep_items = [
        DependencyItem(
            owner="STASH",
            name="CALLER_PROC",
            object_type="PROCEDURE",
            referenced_owner="STASH",
            referenced_name="MY_PKG",
            referenced_type="PACKAGE BODY",
        )
    ]

    with (
        patch.object(analyzer, "query_references", return_value=ref_items),
        patch.object(analyzer, "query_dependents", return_value=dep_items),
    ):
        report = analyzer.analyze(
            owner="STASH",
            name="MY_PKG",
            object_type="PACKAGE BODY",
            direction="both",
            max_depth=3,
        )

    assert report.target_name == "MY_PKG"
    assert report.direction == "BOTH"
    assert report.total_dependencies == 2
    assert report.references_tree is not None
    assert report.dependents_tree is not None


def test_format_dependency_text() -> None:
    """Test text rendering of dependency report."""
    report = ObjectDependencyReport(
        generated_at="2026-09-23T12:00:00Z",
        target_owner="STASH",
        target_name="MY_PKG",
        target_type="PACKAGE BODY",
        direction="BOTH",
        max_depth=3,
        total_dependencies=1,
        references_tree=DependencyTreeNode(
            owner="STASH",
            name="MY_PKG",
            object_type="PACKAGE BODY",
            children=[
                DependencyTreeNode(
                    owner="STASH",
                    name="SCENES",
                    object_type="TABLE",
                    depth=1,
                )
            ],
        ),
        dependents_tree=DependencyTreeNode(
            owner="STASH",
            name="MY_PKG",
            object_type="PACKAGE BODY",
            children=[],
        ),
        direct_items=[],
    )

    text = format_dependency_text(report)
    assert "Oracle Object Dependency Report" in text
    assert "STASH.MY_PKG (PACKAGE BODY)" in text
    assert "UPSTREAM DEPENDENCIES" in text
    assert "└── STASH.SCENES (TABLE)" in text
    assert "No dependent objects found" in text


def test_main_cli_missing_credentials() -> None:
    """Test CLI exit code on missing credentials."""
    ret = main(["--name", "SCENES"])
    assert ret == 1


def test_main_cli_success(tmp_path: Path) -> None:
    """Test CLI happy path writing to output file."""
    out_file = tmp_path / "deps.txt"

    with patch.object(
        ObjectDependencyAnalyzer,
        "analyze",
        return_value=ObjectDependencyReport(
            generated_at="2026-09-23T12:00:00Z",
            target_owner="STASH",
            target_name="SCENES",
            target_type="TABLE",
            direction="BOTH",
            max_depth=3,
            total_dependencies=0,
            references_tree=DependencyTreeNode(
                owner="STASH",
                name="SCENES",
                object_type="TABLE",
            ),
            dependents_tree=DependencyTreeNode(
                owner="STASH",
                name="SCENES",
                object_type="TABLE",
            ),
            direct_items=[],
        ),
    ):
        ret = main(
            [
                "--user",
                "stash",
                "--password",
                "password",
                "--name",
                "SCENES",
                "--output-file",
                str(out_file),
            ]
        )

    assert ret == 0
    assert out_file.exists()
    assert "Oracle Object Dependency Report" in out_file.read_text(encoding="utf-8")
