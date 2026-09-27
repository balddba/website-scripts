#!/usr/bin/env python3
#===============================================================================
#
# Script Name: find_low_cardinality_indexes.py
# Title: Find low-cardinality Oracle indexes
# Tags: Python, Indexes, Performance
# Purpose: Identify Oracle indexes with low cardinality or poor selectivity.
#
# Description:
#   Examines index statistics and reports candidates that may benefit from
#   review, with filters for schema, table, index, and selectivity threshold.
#
# Parameters:
#   Command-line Oracle connection settings and index filters; use --help.
#
# Required Privileges:
#   - Read access to the Oracle catalog views queried by the script
#
# Output Format:
#   - Index analysis written to standard output or the requested output file
#
# Example Usage:
#   python find_low_cardinality_indexes.py --help
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
"""Analyze Oracle database indexes for low-cardinality and sub-optimal selectivity."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import oracledb
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
        owner: Optional schema owner filter.
        table_name: Optional table name filter.
        index_name: Optional index name filter.
        threshold_pct: Selectivity ratio percentage threshold.
        min_rows: Minimum table row count threshold for analysis.
    """

    model_config = {"extra": "forbid"}

    hostname: str = Field(default="localhost", description="Database hostname")
    port: int = Field(default=1521, description="Database port")
    service_name: str | None = Field(default=None, description="Oracle service name")
    sid: str | None = Field(default=None, description="Oracle SID")
    username: str = Field(..., description="Database username")
    password: SecretStr = Field(..., description="Database password")
    is_sysdba: bool = Field(default=False, description="Connect with SYSDBA mode")
    owner: str | None = Field(default=None, description="Schema owner filter")
    table_name: str | None = Field(default=None, description="Table name filter")
    index_name: str | None = Field(default=None, description="Index name filter")
    threshold_pct: float = Field(
        default=5.0,
        ge=0.0,
        le=100.0,
        description="Selectivity ratio percentage threshold",
    )
    min_rows: int = Field(
        default=1000,
        ge=0,
        description="Minimum table rows threshold",
    )


class LowCardinalityIndex(BaseModel):
    """Representation of an Oracle index with cardinality metrics and recommendations.

    Attributes:
        owner: Schema owner of the index.
        index_name: Name of the index.
        table_owner: Schema owner of the associated table.
        table_name: Name of the associated table.
        index_type: Type of index (e.g. NORMAL, BITMAP).
        uniqueness: Index uniqueness constraint status (UNIQUE or NONUNIQUE).
        columns: List of column names in indexed order.
        num_rows: Total row count of table or index.
        distinct_keys: Number of distinct indexed keys.
        selectivity_ratio_pct: Percentage ratio of distinct keys to total rows.
        blevel: B-tree level (depth from root to leaf blocks).
        leaf_blocks: Number of leaf blocks in index.
        clustering_factor: Index clustering factor relative to table blocks.
        recommendations: Actionable tuning and optimization recommendations.
    """

    model_config = {"extra": "forbid"}

    owner: str
    index_name: str
    table_owner: str
    table_name: str
    index_type: str = "NORMAL"
    uniqueness: str = "NONUNIQUE"
    columns: list[str] = Field(default_factory=list)
    num_rows: int
    distinct_keys: int
    selectivity_ratio_pct: float
    blevel: int | None = None
    leaf_blocks: int | None = None
    clustering_factor: int | None = None
    recommendations: list[str] = Field(default_factory=list)


class LowCardinalityReport(BaseModel):
    """Consolidated low-cardinality index analysis report.

    Attributes:
        generated_at: Timestamp when report was generated in UTC.
        threshold_pct: Selectivity ratio percentage threshold used.
        min_rows: Minimum table row count threshold used.
        owner_filter: Schema owner filter applied if any.
        table_filter: Table name filter applied if any.
        index_filter: Index name filter applied if any.
        total_indexes_evaluated: Total count of indexes meeting row count criteria.
        low_cardinality_count: Total count of indexes flagged as low cardinality.
        items: List of flagged low-cardinality index objects.
    """

    model_config = {"extra": "forbid"}

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    threshold_pct: float
    min_rows: int
    owner_filter: str | None = None
    table_filter: str | None = None
    index_filter: str | None = None
    total_indexes_evaluated: int
    low_cardinality_count: int
    items: list[LowCardinalityIndex] = Field(default_factory=list)


class OracleDriver:
    """Manages connections and session lifecycle for Oracle database."""

    def __init__(self, config: OracleConnectionConfig) -> None:
        """Initialize the Oracle driver with connection settings.

        Args:
            config (OracleConnectionConfig): Oracle connection settings and credentials.
        """
        self._config = config

    @contextmanager
    def session(self) -> Generator[oracledb.Connection, None, None]:
        """Open and yield an Oracle database connection.

        Yields:
            oracledb.Connection: Active database connection.

        Raises:
            oracledb.DatabaseError: If connection fails.
        """
        if self._config.service_name:
            dsn = oracledb.makedsn(
                self._config.hostname,
                self._config.port,
                service_name=self._config.service_name,
            )
        elif self._config.sid:
            dsn = oracledb.makedsn(
                self._config.hostname,
                self._config.port,
                sid=self._config.sid,
            )
        else:
            dsn = f"{self._config.hostname}:{self._config.port}"

        mode = oracledb.SYSDBA if (self._config.is_sysdba or self._config.username.upper() == "SYS") else 0
        password = self._config.password.get_secret_value()

        logger.bind(
            host=self._config.hostname,
            port=self._config.port,
            user=self._config.username,
        ).info("Connecting to Oracle database")

        try:
            with oracledb.connect(
                user=self._config.username,
                password=password,
                dsn=dsn,
                mode=mode,
            ) as conn:
                yield conn
        except oracledb.DatabaseError as exc:
            logger.bind(
                host=self._config.hostname,
                port=self._config.port,
                user=self._config.username,
            ).error("Database connection failed: {}", exc)
            raise


class LowCardinalityIndexAnalyzer:
    """Analyzer service for discovering and evaluating low-cardinality Oracle indexes."""

    def __init__(
        self,
        driver: OracleDriver,
        threshold_pct: float = 5.0,
        min_rows: int = 1000,
        owner_filter: str | None = None,
        table_filter: str | None = None,
        index_filter: str | None = None,
    ) -> None:
        """Initialize the low cardinality index analyzer.

        Args:
            driver (OracleDriver): Oracle database session driver.
            threshold_pct (float): Selectivity percentage cutoff threshold.
            min_rows (int): Minimum table row threshold.
            owner_filter (str | None): Optional schema owner filter.
            table_filter (str | None): Optional table name filter.
            index_filter (str | None): Optional index name filter.
        """
        self._driver = driver
        self._threshold_pct = threshold_pct
        self._min_rows = min_rows
        self._owner_filter = owner_filter.upper() if owner_filter else None
        self._table_filter = table_filter.upper() if table_filter else None
        self._index_filter = index_filter.upper() if index_filter else None

    def analyze(self) -> LowCardinalityReport:
        """Execute queries, calculate index selectivity, and compile recommendations.

        Returns:
            LowCardinalityReport: Consolidated analysis report.
        """
        with self._driver.session() as conn:
            rows = self._fetch_index_data(conn)

        raw_index_map: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            owner = str(row[0])
            index_name = str(row[1])
            key = (owner, index_name)

            if key not in raw_index_map:
                raw_index_map[key] = {
                    "owner": owner,
                    "index_name": index_name,
                    "index_type": str(row[2]) if row[2] else "NORMAL",
                    "table_owner": str(row[3]) if row[3] else owner,
                    "table_name": str(row[4]),
                    "uniqueness": str(row[5]) if row[5] else "NONUNIQUE",
                    "blevel": int(row[6]) if row[6] is not None else None,
                    "leaf_blocks": int(row[7]) if row[7] is not None else None,
                    "distinct_keys": int(row[8]) if row[8] is not None else None,
                    "clustering_factor": int(row[9]) if row[9] is not None else None,
                    "num_rows": int(row[10]) if row[10] is not None else 0,
                    "columns": [],
                }

            col_name = str(row[11]) if row[11] is not None else ""
            if col_name and col_name not in raw_index_map[key]["columns"]:
                raw_index_map[key]["columns"].append(col_name)

        total_evaluated = 0
        flagged_items: list[LowCardinalityIndex] = []

        for item_data in raw_index_map.values():
            num_rows = item_data["num_rows"]
            if num_rows < self._min_rows:
                continue

            total_evaluated += 1
            distinct_keys = item_data["distinct_keys"] if item_data["distinct_keys"] is not None else 0

            selectivity_ratio_pct = (distinct_keys / num_rows) * 100.0 if num_rows > 0 else 0.0
            selectivity_ratio_pct = round(selectivity_ratio_pct, 4)

            if selectivity_ratio_pct <= self._threshold_pct:
                recs = self._generate_recommendations(
                    index_type=item_data["index_type"],
                    uniqueness=item_data["uniqueness"],
                    selectivity_ratio_pct=selectivity_ratio_pct,
                    distinct_keys=distinct_keys,
                    num_rows=num_rows,
                    blevel=item_data["blevel"],
                    clustering_factor=item_data["clustering_factor"],
                )

                flagged_items.append(
                    LowCardinalityIndex(
                        owner=item_data["owner"],
                        index_name=item_data["index_name"],
                        table_owner=item_data["table_owner"],
                        table_name=item_data["table_name"],
                        index_type=item_data["index_type"],
                        uniqueness=item_data["uniqueness"],
                        columns=item_data["columns"],
                        num_rows=num_rows,
                        distinct_keys=distinct_keys,
                        selectivity_ratio_pct=selectivity_ratio_pct,
                        blevel=item_data["blevel"],
                        leaf_blocks=item_data["leaf_blocks"],
                        clustering_factor=item_data["clustering_factor"],
                        recommendations=recs,
                    )
                )

        flagged_items.sort(key=lambda x: (x.selectivity_ratio_pct, x.owner, x.table_name, x.index_name))

        return LowCardinalityReport(
            threshold_pct=self._threshold_pct,
            min_rows=self._min_rows,
            owner_filter=self._owner_filter,
            table_filter=self._table_filter,
            index_filter=self._index_filter,
            total_indexes_evaluated=total_evaluated,
            low_cardinality_count=len(flagged_items),
            items=flagged_items,
        )

    def _fetch_index_data(self, conn: oracledb.Connection) -> list[tuple[Any, ...]]:
        """Fetch index metadata, table rows, and indexed columns from Oracle catalog.

        Args:
            conn (oracledb.Connection): Active Oracle connection.

        Returns:
            list[tuple[Any, ...]]: Raw rows containing index definitions and stats.
        """
        sql_dba = """
            SELECT
                i.owner,
                i.index_name,
                i.index_type,
                i.table_owner,
                i.table_name,
                i.uniqueness,
                i.blevel,
                i.leaf_blocks,
                i.distinct_keys,
                i.clustering_factor,
                COALESCE(i.num_rows, t.num_rows, 0) AS num_rows,
                ic.column_name,
                ic.column_position,
                ic.descend
            FROM dba_indexes i
            JOIN dba_tables t
                ON i.table_owner = t.owner
               AND i.table_name = t.table_name
            JOIN dba_ind_columns ic
                ON i.owner = ic.index_owner
               AND i.index_name = ic.index_name
            WHERE (:owner IS NULL OR i.owner = :owner)
              AND (:table_name IS NULL OR i.table_name = :table_name)
              AND (:index_name IS NULL OR i.index_name = :index_name)
              AND i.index_type NOT LIKE '%LOB%'
              AND i.index_type NOT LIKE '%IOT%'
            ORDER BY i.owner, i.table_name, i.index_name, ic.column_position
        """

        sql_all = """
            SELECT
                i.owner,
                i.index_name,
                i.index_type,
                i.table_owner,
                i.table_name,
                i.uniqueness,
                i.blevel,
                i.leaf_blocks,
                i.distinct_keys,
                i.clustering_factor,
                COALESCE(i.num_rows, t.num_rows, 0) AS num_rows,
                ic.column_name,
                ic.column_position,
                ic.descend
            FROM all_indexes i
            JOIN all_tables t
                ON i.table_owner = t.owner
               AND i.table_name = t.table_name
            JOIN all_ind_columns ic
                ON i.owner = ic.index_owner
               AND i.index_name = ic.index_name
            WHERE (:owner IS NULL OR i.owner = :owner)
              AND (:table_name IS NULL OR i.table_name = :table_name)
              AND (:index_name IS NULL OR i.index_name = :index_name)
              AND i.index_type NOT LIKE '%LOB%'
              AND i.index_type NOT LIKE '%IOT%'
            ORDER BY i.owner, i.table_name, i.index_name, ic.column_position
        """

        bind_params: dict[str, Any] = {
            "owner": self._owner_filter,
            "table_name": self._table_filter,
            "index_name": self._index_filter,
        }

        return self._query_with_fallback(conn, sql_dba, sql_all, bind_params)

    def _query_with_fallback(
        self,
        conn: oracledb.Connection,
        primary_sql: str,
        fallback_sql: str,
        params: dict[str, Any],
    ) -> list[tuple[Any, ...]]:
        """Execute a query with fallback to ALL_ views if DBA_ views are inaccessible.

        Args:
            conn (oracledb.Connection): Active Oracle connection.
            primary_sql (str): Primary SQL referencing DBA_ catalog views.
            fallback_sql (str): Fallback SQL referencing ALL_ catalog views.
            params (dict[str, Any]): Named bind parameter dictionary.

        Returns:
            list[tuple[Any, ...]]: Result rows.

        Raises:
            oracledb.DatabaseError: If catalog queries fail.
        """
        with conn.cursor() as cursor:
            try:
                cursor.execute(primary_sql, params)
                return cursor.fetchall()
            except oracledb.DatabaseError as exc:
                err_obj = exc.args[0] if exc.args else None
                err_code = getattr(err_obj, "code", 0)
                # ORA-00942: table or view does not exist
                if err_code == 942:
                    logger.warning("DBA view inaccessible (ORA-00942), falling back to ALL_ catalog view")
                    try:
                        cursor.execute(fallback_sql, params)
                        return cursor.fetchall()
                    except oracledb.DatabaseError as fallback_exc:
                        logger.error("Fallback query failed: {}", fallback_exc)
                        raise
                logger.error("Catalog query failed: {}", exc)
                raise

    @staticmethod
    def _generate_recommendations(
        index_type: str,
        uniqueness: str,
        selectivity_ratio_pct: float,
        distinct_keys: int,
        num_rows: int,
        blevel: int | None,
        clustering_factor: int | None,
    ) -> list[str]:
        """Generate actionable performance and tuning recommendations for an index.

        Args:
            index_type (str): Type of index (e.g. NORMAL, BITMAP).
            uniqueness (str): Uniqueness status (UNIQUE or NONUNIQUE).
            selectivity_ratio_pct (float): Ratio of distinct keys to total rows.
            distinct_keys (int): Number of distinct keys.
            num_rows (int): Number of rows in the table.
            blevel (int | None): B-tree depth level.
            clustering_factor (int | None): Clustering factor.

        Returns:
            list[str]: Actionable recommendations.
        """
        recs: list[str] = []

        if distinct_keys <= 1:
            recs.append("Distinct keys <= 1 indicates a constant or single-value column; this index provides no selective filtering benefit and incurs write overhead.")
        elif selectivity_ratio_pct < 0.1 and uniqueness != "UNIQUE":
            recs.append(f"Extremely low selectivity ({selectivity_ratio_pct:.4f}%); index provides minimal filtering efficiency and the optimizer will likely prefer full table scans.")
        elif selectivity_ratio_pct <= 1.0 and uniqueness != "UNIQUE":
            recs.append(f"Low selectivity ({selectivity_ratio_pct:.2f}%); consider reviewing query access patterns or combining with higher-cardinality columns into a composite index.")

        if index_type == "NORMAL" and uniqueness != "UNIQUE" and selectivity_ratio_pct <= 5.0:
            recs.append("Candidate for Bitmap index conversion if used in low-DML reporting, data warehouse, or decision-support workloads (avoid on high-concurrency OLTP tables due to row-lock contention).")

        if clustering_factor is not None and num_rows > 0 and clustering_factor >= int(0.85 * num_rows):
            recs.append(f"High clustering factor ({clustering_factor:,} vs {num_rows:,} rows) indicates index row order is scattered across blocks; multi-row index range scans will incur excessive disk I/O.")

        if blevel is not None and blevel >= 4:
            recs.append(f"High B-tree depth (blevel={blevel}); evaluate index fragmentation and consider rebuilding or coalescing index blocks.")

        if uniqueness == "UNIQUE":
            recs.append("Index enforces a unique constraint; cannot be converted to bitmap or dropped without altering constraint definitions.")

        return recs


def format_report_text(report: LowCardinalityReport) -> str:
    """Format the low-cardinality index report into human-readable text.

    Args:
        report (LowCardinalityReport): Analysis report containing evaluated index metrics.

    Returns:
        str: Formatted human-readable report string.
    """
    now_str = report.generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "=" * 80,
        " ORACLE LOW-CARDINALITY INDEX ANALYSIS REPORT",
        f" Generated: {now_str}",
        "=" * 80,
        " Configuration & Filters:",
        f"   - Selectivity Threshold: <= {report.threshold_pct:.2f}%",
        f"   - Minimum Table Rows:    {report.min_rows:,}",
        f"   - Owner Filter:          {report.owner_filter or 'ALL'}",
        f"   - Table Filter:          {report.table_filter or 'ALL'}",
        f"   - Index Filter:          {report.index_filter or 'ALL'}",
        "",
        " Summary:",
        f"   - Total Evaluated Indexes: {report.total_indexes_evaluated:,}",
        f"   - Low-Cardinality Indexes:  {report.low_cardinality_count:,}",
        "",
    ]

    if not report.items:
        lines.append("-" * 80)
        lines.append(" No low-cardinality indexes found matching the criteria.")
        lines.append("-" * 80)
        return "\n".join(lines)

    lines.append("-" * 80)
    lines.append(" TABULAR SUMMARY")
    lines.append("-" * 80)

    header = f"{'INDEX NAME':<26} {'TABLE NAME':<22} {'DIST KEYS':>10} {'NUM ROWS':>10} {'SELECTIVITY':>12} {'UNIQUENESS':<10}"
    lines.append(header)
    lines.append("-" * len(header))

    for item in report.items:
        idx_display = item.index_name[:24] + ".." if len(item.index_name) > 26 else item.index_name
        tbl_display = item.table_name[:20] + ".." if len(item.table_name) > 22 else item.table_name
        lines.append(f"{idx_display:<26} {tbl_display:<22} {item.distinct_keys:>10,} {item.num_rows:>10,} {item.selectivity_ratio_pct:>11.4f}% {item.uniqueness:<10}")

    lines.append("")
    lines.append("-" * 80)
    lines.append(" ACTIONABLE RECOMMENDATIONS & DETAILED BREAKDOWN")
    lines.append("-" * 80)

    for idx, item in enumerate(report.items, start=1):
        cols_str = ", ".join(item.columns) if item.columns else "N/A"
        blevel_str = str(item.blevel) if item.blevel is not None else "N/A"
        leaf_str = f"{item.leaf_blocks:,}" if item.leaf_blocks is not None else "N/A"
        clust_str = f"{item.clustering_factor:,}" if item.clustering_factor is not None else "N/A"

        lines.extend(
            [
                f"[{idx}] {item.owner}.{item.index_name}",
                f"    Table:             {item.table_owner}.{item.table_name}",
                f"    Columns:           {cols_str}",
                f"    Type:              {item.index_type} ({item.uniqueness})",
                f"    Num Rows:          {item.num_rows:,}",
                f"    Distinct Keys:     {item.distinct_keys:,}",
                f"    Selectivity:       {item.selectivity_ratio_pct:.4f}%",
                f"    B-Tree Level:      {blevel_str}",
                f"    Leaf Blocks:       {leaf_str}",
                f"    Clustering Factor: {clust_str}",
            ]
        )

        if item.recommendations:
            lines.append("    Recommendations:")
            for rec in item.recommendations:
                lines.append(f"      * {rec}")
        else:
            lines.append("    Recommendations: None")
        lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build and configure command-line argument parser.

    Returns:
        argparse.ArgumentParser: Configured argument parser.
    """
    parser = argparse.ArgumentParser(description="Analyze Oracle database indexes for low-cardinality and sub-optimal selectivity.")
    parser.add_argument(
        "--host",
        default=os.getenv("ORACLE_HOST", "localhost"),
        help="Oracle database hostname (default: ORACLE_HOST or localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ORACLE_PORT", "1521")),
        help="Oracle database port (default: ORACLE_PORT or 1521)",
    )
    parser.add_argument(
        "--service-name",
        default=os.getenv("ORACLE_SERVICE_NAME"),
        help="Oracle service name (default: ORACLE_SERVICE_NAME)",
    )
    parser.add_argument(
        "--sid",
        default=os.getenv("ORACLE_SID"),
        help="Oracle SID (default: ORACLE_SID)",
    )
    parser.add_argument(
        "--user",
        default=os.getenv("ORACLE_USER"),
        help="Database username (default: ORACLE_USER)",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("ORACLE_PASSWORD"),
        help="Database password (default: ORACLE_PASSWORD)",
    )
    parser.add_argument(
        "--sysdba",
        action="store_true",
        help="Connect with SYSDBA privilege",
    )
    parser.add_argument(
        "--owner",
        default=os.getenv("ORACLE_OWNER"),
        help="Filter by schema owner (default: all schemas accessible)",
    )
    parser.add_argument(
        "--table",
        default=os.getenv("ORACLE_TABLE"),
        help="Filter by table name (default: all tables)",
    )
    parser.add_argument(
        "--index",
        default=os.getenv("ORACLE_INDEX"),
        help="Filter by index name (default: all indexes)",
    )
    parser.add_argument(
        "--threshold-pct",
        type=float,
        default=float(os.getenv("ORACLE_THRESHOLD_PCT", "5.0")),
        help="Selectivity threshold percentage below which indexes are flagged (default: 5.0)",
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=int(os.getenv("ORACLE_MIN_ROWS", "1000")),
        help="Minimum table row count required for index evaluation (default: 1000)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output report in JSON format",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="File path to save the output report",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI execution entrypoint.

    Args:
        argv (list[str] | None): Optional command-line arguments list.

    Returns:
        int: Exit status code (0 = clean / no low cardinality indexes, 2 = low cardinality indexes found, 1 = error).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.user:
        logger.error("Database username must be specified via --user or ORACLE_USER")
        return 1
    if not args.password:
        logger.error("Database password must be specified via --password or ORACLE_PASSWORD")
        return 1
    if not args.service_name and not args.sid:
        logger.error("Either --service-name or --sid must be specified (or via environment variables)")
        return 1

    try:
        config = OracleConnectionConfig(
            hostname=args.host,
            port=args.port,
            service_name=args.service_name,
            sid=args.sid,
            username=args.user,
            password=SecretStr(args.password),
            is_sysdba=args.sysdba,
            owner=args.owner,
            table_name=args.table,
            index_name=args.index,
            threshold_pct=args.threshold_pct,
            min_rows=args.min_rows,
        )
    except ValidationError as exc:
        logger.error("Configuration validation failed: {}", exc)
        return 1

    driver = OracleDriver(config)
    analyzer = LowCardinalityIndexAnalyzer(
        driver=driver,
        threshold_pct=config.threshold_pct,
        min_rows=config.min_rows,
        owner_filter=config.owner,
        table_filter=config.table_name,
        index_filter=config.index_name,
    )

    try:
        report = analyzer.analyze()
    except oracledb.DatabaseError as exc:
        logger.error("Database error while analyzing indexes: {}", exc)
        return 1

    if args.json_output:
        output_text = report.model_dump_json(indent=2)
    else:
        output_text = format_report_text(report)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_text)
            logger.info("Report saved to {}", args.output)
        except OSError as exc:
            logger.error("Failed to write report to {}: {}", args.output, exc)
            return 1
    else:
        sys.stdout.write(output_text + "\n")

    return 0 if report.low_cardinality_count == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
