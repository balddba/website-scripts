#!/usr/bin/env python3
#===============================================================================
#
# Script Name: replication_report.py
# Title: Redis replication information
# Tags: Redis, Python, Replication, High Availability
# Purpose: Displays replication role, health, offsets, lag, and backlog details.
#
# Description:
#   Reads INFO replication from one Redis node. For a primary, it lists each
#   connected replica and its offset and lag. For a replica, it reports the
#   upstream primary link, synchronization state, read-only setting, and offset.
#   In Redis Cluster, the report describes only the node addressed by the URL.
#
# Parameters:
#   --url URL          Redis URL (default: REDIS_URL or redis://localhost:6379/0)
#   --max-lag SECONDS  Replica lag warning threshold (default: 10)
#
# Required Privileges:
#   - Permission to connect, PING, and run INFO replication
#   - Python package redis (`python -m pip install redis`)
#
# Output Format:
#   - Human-readable replication role, topology, health, and backlog report
#
# Example Usage:
#   python replication_report.py
#   python replication_report.py --url redis://replica.example.com:6379/0 --max-lag 5
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
"""Display Redis replication role, topology, health, offsets, and lag."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from typing import Any


def nonnegative_integer(value: str) -> int:
    """Validate a nonnegative integer argument."""
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    parser.add_argument(
        "--max-lag",
        type=nonnegative_integer,
        default=10,
        help="replica lag warning threshold in seconds (default: 10)",
    )
    return parser.parse_args(argv)


def as_integer(value: Any, default: int = 0) -> int:
    """Convert an INFO value to an integer."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def yes_no(value: Any) -> str:
    """Format Redis boolean-like values."""
    return "yes" if value in {1, "1", "yes"} else "no"


def replica_rows(info: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    """Return replica records from a primary INFO response."""
    rows = []
    for key, value in info.items():
        if key.startswith(("slave", "replica")) and isinstance(value, Mapping):
            rows.append((key, value))
    return sorted(rows, key=lambda item: item[0])


def print_primary(info: Mapping[str, Any], max_lag: int) -> list[str]:
    """Print primary-side replication information and return warnings."""
    warnings = []
    primary_offset = as_integer(info.get("master_repl_offset"))
    replicas = replica_rows(info)

    print(f"Connected replicas : {info.get('connected_slaves', len(replicas))}")
    print(f"Failover state     : {info.get('master_failover_state', 'n/a')}")
    print(f"Replication ID     : {info.get('master_replid', 'n/a')}")
    print(f"Primary offset     : {primary_offset}")

    print("\nReplicas")
    print("--------")
    if not replicas:
        print("No connected replicas reported.")
        return warnings

    for name, replica in replicas:
        replica_offset = as_integer(replica.get("offset"))
        lag = as_integer(replica.get("lag"), -1)
        offset_delta = max(0, primary_offset - replica_offset)
        address = f"{replica.get('ip', 'unknown')}:{replica.get('port', 'unknown')}"
        state = replica.get("state", "unknown")
        print(f"{name} {address}")
        print(f"  State        : {state}")
        print(f"  Offset       : {replica_offset}")
        print(f"  Offset delta : {offset_delta}")
        print(f"  Lag          : {lag if lag >= 0 else 'n/a'} seconds")
        if state != "online":
            warnings.append(f"{name} state is {state}")
        if lag > max_lag:
            warnings.append(f"{name} lag is {lag} seconds")
    return warnings


def print_replica(info: Mapping[str, Any], max_lag: int) -> list[str]:
    """Print replica-side replication information and return warnings."""
    warnings = []
    link_status = str(info.get("master_link_status", "unknown"))
    last_io = as_integer(info.get("master_last_io_seconds_ago"), -1)
    syncing = yes_no(info.get("master_sync_in_progress"))

    print(f"Primary            : {info.get('master_host', 'unknown')}:{info.get('master_port', 'unknown')}")
    print(f"Primary link       : {link_status}")
    print(f"Last primary I/O   : {last_io if last_io >= 0 else 'n/a'} seconds ago")
    print(f"Sync in progress   : {syncing}")
    print(f"Replica read-only  : {yes_no(info.get('slave_read_only', info.get('replica_read_only')))}")
    print(f"Replica offset     : {info.get('slave_repl_offset', info.get('replica_repl_offset', 'n/a'))}")
    print(f"Primary offset     : {info.get('master_repl_offset', 'n/a')}")
    print(f"Replica priority   : {info.get('slave_priority', info.get('replica_priority', 'n/a'))}")

    if link_status != "up":
        warnings.append(f"primary link is {link_status}")
    if syncing == "yes":
        warnings.append("initial synchronization is in progress")
    if last_io > max_lag:
        warnings.append(f"last primary I/O was {last_io} seconds ago")
    return warnings


def print_backlog(info: Mapping[str, Any]) -> None:
    """Print replication backlog details."""
    print("\nBacklog")
    print("-------")
    print(f"Active       : {yes_no(info.get('repl_backlog_active'))}")
    print(f"Size         : {info.get('repl_backlog_size', 'n/a')} bytes")
    print(f"History size : {info.get('repl_backlog_histlen', 'n/a')} bytes")
    print(f"First offset : {info.get('repl_backlog_first_byte_offset', 'n/a')}")


def main(argv: Sequence[str] | None = None) -> int:
    """Query Redis and print replication information."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        import redis
    except ImportError:
        print("ERROR: install redis-py with: python -m pip install redis", file=sys.stderr)
        return 2

    client = redis.Redis.from_url(
        args.url,
        decode_responses=True,
        socket_connect_timeout=2.0,
        socket_timeout=5.0,
    )
    try:
        info = client.info("replication")
    except redis.RedisError as exc:
        print(f"ERROR: unable to read Redis replication information: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()

    role = str(info.get("role", "unknown"))
    print("Redis Replication Information")
    print("=============================")
    print(f"Role               : {role}")

    if role == "master":
        warnings = print_primary(info, args.max_lag)
    elif role in {"slave", "replica"}:
        warnings = print_replica(info, args.max_lag)
    else:
        warnings = [f"unrecognized replication role: {role}"]

    print_backlog(info)
    print("\nStatus: " + ("WARNING - " + "; ".join(warnings) if warnings else "OK"))
    return 1 if warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
