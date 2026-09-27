#!/usr/bin/env python3
#===============================================================================
#
# Script Name: redis_server_info.py
# Title: Redis server information
# Tags: Redis, Python, Monitoring, Server Info
# Purpose: Displays a concise health and configuration summary for a Redis server.
#
# Description:
#   Connects to Redis with redis-py, reads the INFO response, and prints key
#   server, client, memory, activity, persistence, replication, cluster, and
#   keyspace metrics. Credentials are never included in the report.
#
# Parameters:
#   --url              Redis URL (default: REDIS_URL or redis://localhost:6379/0)
#   --connect-timeout  Connection timeout in seconds (default: 2.0)
#   --socket-timeout   Command timeout in seconds (default: 5.0)
#
# Required Privileges:
#   - Permission to connect, PING, and run INFO
#   - Python package redis (`python -m pip install redis`)
#
# Output Format:
#   - Human-readable server information grouped by category
#
# Example Usage:
#   python redis_server_info.py
#   REDIS_URL='rediss://user:password@redis.example.com:6379/0' python redis_server_info.py
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
"""Display basic health and configuration information for a Redis server."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        help="Redis URL (default: REDIS_URL or redis://localhost:6379/0)",
    )
    parser.add_argument(
        "--connect-timeout",
        type=positive_float,
        default=2.0,
        help="connection timeout in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--socket-timeout",
        type=positive_float,
        default=5.0,
        help="command timeout in seconds (default: 5.0)",
    )
    return parser.parse_args(argv)


def positive_float(value: str) -> float:
    """Return a positive float for argparse."""
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def safe_endpoint(url: str) -> str:
    """Return a connection endpoint without credentials."""
    parsed = urlsplit(url)
    scheme = parsed.scheme or "redis"
    host = parsed.hostname or "localhost"
    port = parsed.port or (6380 if scheme == "rediss" else 6379)
    database = parsed.path.lstrip("/") or "0"
    return f"{scheme}://{host}:{port}/{database}"


def percentage(numerator: int, denominator: int) -> str:
    """Format a ratio as a percentage, handling an empty denominator."""
    if denominator == 0:
        return "n/a"
    return f"{numerator / denominator:.1%}"


def timestamp(value: Any) -> str:
    """Format a Unix timestamp as UTC or return n/a."""
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return "n/a"


def display_value(value: Any, default: str = "n/a") -> str:
    """Convert an INFO value to display text."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def duration_days(value: Any) -> str:
    """Format an uptime value from INFO."""
    if value is None:
        return "n/a"
    return f"{value} days"


def print_section(title: str, rows: Sequence[tuple[str, Any]]) -> None:
    """Print one aligned report section."""
    print(f"\n{title}")
    print("-" * len(title))
    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        print(f"{label:<{width}} : {display_value(value)}")


def print_report(endpoint: str, info: Mapping[str, Any]) -> None:
    """Print selected Redis INFO metrics."""
    hits = int(info.get("keyspace_hits", 0))
    misses = int(info.get("keyspace_misses", 0))

    print("Redis Server Information")
    print("=" * 24)
    print(f"Endpoint : {endpoint}")

    print_section(
        "Server",
        (
            ("Redis version", info.get("redis_version")),
            ("Mode", info.get("redis_mode")),
            ("Operating system", info.get("os")),
            ("Architecture", f"{info.get('arch_bits', 'n/a')}-bit"),
            ("Process ID", info.get("process_id")),
            ("Uptime", duration_days(info.get("uptime_in_days"))),
        ),
    )
    print_section(
        "Clients",
        (
            ("Connected", info.get("connected_clients")),
            ("Blocked", info.get("blocked_clients")),
            ("Tracking", info.get("tracking_clients")),
            ("Rejected connections", info.get("rejected_connections")),
        ),
    )
    print_section(
        "Memory",
        (
            ("Used", info.get("used_memory_human")),
            ("Peak", info.get("used_memory_peak_human")),
            ("Maximum", info.get("maxmemory_human")),
            ("Fragmentation ratio", info.get("mem_fragmentation_ratio")),
        ),
    )
    print_section(
        "Activity",
        (
            ("Operations/sec", info.get("instantaneous_ops_per_sec")),
            ("Commands processed", info.get("total_commands_processed")),
            ("Keyspace hits", hits),
            ("Keyspace misses", misses),
            ("Cache hit ratio", percentage(hits, hits + misses)),
            ("Expired keys", info.get("expired_keys")),
            ("Evicted keys", info.get("evicted_keys")),
        ),
    )
    print_section(
        "Persistence",
        (
            ("RDB changes since save", info.get("rdb_changes_since_last_save")),
            ("RDB save in progress", bool(info.get("rdb_bgsave_in_progress", 0))),
            ("Last RDB save", timestamp(info.get("rdb_last_save_time"))),
            ("Last RDB status", info.get("rdb_last_bgsave_status")),
            ("AOF enabled", bool(info.get("aof_enabled", 0))),
        ),
    )
    print_section(
        "Topology",
        (
            ("Role", info.get("role")),
            ("Connected replicas", info.get("connected_slaves")),
            ("Cluster enabled", bool(info.get("cluster_enabled", 0))),
        ),
    )

    keyspaces = sorted(
        (key, value)
        for key, value in info.items()
        if key.startswith("db") and isinstance(value, Mapping)
    )
    if keyspaces:
        print_section(
            "Keyspace",
            tuple(
                (
                    database,
                    f"{values.get('keys', 0)} keys, {values.get('expires', 0)} expiring",
                )
                for database, values in keyspaces
            ),
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Connect to Redis and print the server report."""
    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        import redis
    except ImportError:
        print(
            "ERROR: redis-py is required; install it with: python -m pip install redis",
            file=sys.stderr,
        )
        return 2

    try:
        client = redis.Redis.from_url(
            args.url,
            decode_responses=True,
            socket_connect_timeout=args.connect_timeout,
            socket_timeout=args.socket_timeout,
        )
        client.ping()
        info = client.info("all")
    except redis.RedisError as exc:
        print(f"ERROR: unable to query {safe_endpoint(args.url)}: {exc}", file=sys.stderr)
        return 1
    finally:
        if "client" in locals():
            client.close()

    print_report(safe_endpoint(args.url), info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
