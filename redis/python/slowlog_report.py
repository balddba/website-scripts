#!/usr/bin/env python3
#===============================================================================
#
# Script Name: slowlog_report.py
# Title: Redis slow command report
# Tags: Redis, Python, Slowlog, Performance
# Purpose: Displays recent commands captured by the Redis slow log.
#
# Description:
#   Reads a bounded number of SLOWLOG entries and prints their timestamp,
#   duration, client identity, and command. This script never resets the log.
#
# Parameters:
#   --url URL      Redis URL (default: REDIS_URL or redis://localhost:6379/0)
#   --limit COUNT  Number of entries to return, from 1 to 1000 (default: 10)
#
# Required Privileges:
#   - Permission to connect, PING, SLOWLOG LEN, and SLOWLOG GET
#   - Python package redis (`python -m pip install redis`)
#
# Output Format:
#   - One block per slowlog entry, newest first
#
# Example Usage:
#   python slowlog_report.py --limit 20
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
"""Display recent Redis slowlog entries."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any


def bounded_limit(value: str) -> int:
    """Validate the number of slowlog entries to request."""
    limit = int(value)
    if not 1 <= limit <= 1000:
        raise argparse.ArgumentTypeError("must be between 1 and 1000")
    return limit


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    parser.add_argument("--limit", type=bounded_limit, default=10)
    return parser.parse_args(argv)


def text(value: Any) -> str:
    """Decode a redis-py response value for display."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "-")


def main(argv: Sequence[str] | None = None) -> int:
    """Query Redis and print recent slow commands."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        import redis
    except ImportError:
        print("ERROR: install redis-py with: python -m pip install redis", file=sys.stderr)
        return 2

    client = redis.Redis.from_url(
        args.url,
        socket_connect_timeout=2.0,
        socket_timeout=5.0,
    )
    try:
        total = client.slowlog_len()
        entries = client.slowlog_get(args.limit)
    except redis.RedisError as exc:
        print(f"ERROR: unable to read Redis slowlog: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()

    print(f"Redis Slowlog: showing {len(entries)} of {total} entries")
    print("=" * 52)
    if not entries:
        print("No slow commands recorded.")
        return 0

    for entry in entries:
        started = datetime.fromtimestamp(entry["start_time"], tz=timezone.utc).isoformat()
        print(f"ID       : {entry['id']}")
        print(f"Started  : {started}")
        print(f"Duration : {entry['duration'] / 1000:.3f} ms")
        print(f"Client   : {text(entry.get('client_address'))}")
        print(f"Name     : {text(entry.get('client_name'))}")
        print(f"Command  : {text(entry.get('command'))}")
        print("-" * 52)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
