#!/usr/bin/env python3
#===============================================================================
#
# Script Name: error_diagnostics.py
# Title: Redis error diagnostics
# Tags: Redis, Python, Errors, Troubleshooting
# Purpose: Summarizes Redis errors and common persistence or replication faults.
#
# Description:
#   Reads INFO errorstats, stats, persistence, and replication to highlight
#   command errors, rejected connections, persistence failures, and replica lag.
#
# Parameters:
#   --url URL  Redis URL (default: REDIS_URL or redis://localhost:6379/0)
#
# Required Privileges:
#   - Permission to connect, PING, and run INFO
#   - Python package redis (`python -m pip install redis`)
#
# Output Format:
#   - Error counters and warning-oriented diagnostic summary
#
# Example Usage:
#   python error_diagnostics.py
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
"""Summarize Redis errors and common fault indicators."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Query Redis and print error diagnostics."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        import redis
    except ImportError:
        print("ERROR: install redis-py with: python -m pip install redis", file=sys.stderr)
        return 2

    client = redis.Redis.from_url(args.url, decode_responses=True, socket_connect_timeout=2.0, socket_timeout=5.0)
    try:
        errors = client.info("errorstats")
        stats = client.info("stats")
        persistence = client.info("persistence")
        replication = client.info("replication")
    except redis.RedisError as exc:
        print(f"ERROR: unable to read Redis diagnostics: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()

    print("Redis Error Diagnostics")
    print("=======================")
    print(f"Rejected connections : {stats.get('rejected_connections', 0)}")
    print(f"Expired keys         : {stats.get('expired_keys', 0)}")
    print(f"Evicted keys         : {stats.get('evicted_keys', 0)}")
    print(f"RDB last status      : {persistence.get('rdb_last_bgsave_status', 'n/a')}")
    print(f"AOF last status      : {persistence.get('aof_last_bgrewrite_status', 'n/a')}")
    print(f"Replication role     : {replication.get('role', 'n/a')}")
    print(f"Connected replicas   : {replication.get('connected_slaves', 0)}")

    print("\nError counters")
    print("--------------")
    found = False
    for name, details in sorted(errors.items()):
        if not name.startswith("errorstat_"):
            continue
        found = True
        count = details.get("count", 0) if isinstance(details, Mapping) else details
        print(f"{name.removeprefix('errorstat_'):<20} : {count}")
    if not found:
        print("No command errors reported.")

    warning = (
        int(stats.get("rejected_connections", 0)) > 0
        or persistence.get("rdb_last_bgsave_status") == "err"
        or persistence.get("aof_last_bgrewrite_status") == "err"
    )
    print(f"\nStatus: {'WARNING - investigate the counters above' if warning else 'OK'}")
    return 1 if warning else 0


if __name__ == "__main__":
    raise SystemExit(main())
