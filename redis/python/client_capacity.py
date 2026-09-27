#!/usr/bin/env python3
#===============================================================================
#
# Script Name: client_capacity.py
# Title: Redis client capacity report
# Tags: Redis, Python, Clients, Connections
# Purpose: Compares current Redis client connections with the maxclients limit.
#
# Description:
#   Reads INFO clients and stats, calculates connection utilization, and warns
#   about blocked clients, rejected connections, or high client usage.
#
# Parameters:
#   --url URL  Redis URL (default: REDIS_URL or redis://localhost:6379/0)
#
# Required Privileges:
#   - Permission to connect, PING, and INFO clients/stats
#   - Python package redis (`python -m pip install redis`)
#
# Output Format:
#   - Client counts, maxclients utilization, and warning status
#
# Example Usage:
#   python client_capacity.py
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
"""Compare current Redis connections with maxclients."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Query Redis and print client capacity."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        import redis
    except ImportError:
        print("ERROR: install redis-py with: python -m pip install redis", file=sys.stderr)
        return 2

    client = redis.Redis.from_url(args.url, decode_responses=True, socket_connect_timeout=2.0, socket_timeout=5.0)
    try:
        clients = client.info("clients")
        stats = client.info("stats")
    except redis.RedisError as exc:
        print(f"ERROR: unable to read Redis client information: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()

    connected = int(clients.get("connected_clients", 0))
    maximum = int(clients.get("maxclients", 0))
    utilization = connected / maximum if maximum else 0.0
    blocked = int(clients.get("blocked_clients", 0))
    rejected = int(stats.get("rejected_connections", 0))

    print("Redis Client Capacity")
    print("=====================")
    print(f"Connected clients    : {connected}")
    print(f"Maximum clients      : {maximum or 'unknown'}")
    print(f"Capacity utilization : {utilization:.1%}" if maximum else "Capacity utilization : n/a")
    print(f"Blocked clients      : {blocked}")
    print(f"Tracking clients     : {clients.get('tracking_clients', 0)}")
    print(f"Rejected connections : {rejected}")

    warnings = []
    if utilization >= 0.8:
        warnings.append("client utilization is at or above 80%")
    if blocked:
        warnings.append("one or more clients are blocked")
    if rejected:
        warnings.append("Redis has rejected connections")
    print("Status               : " + ("WARNING - " + "; ".join(warnings) if warnings else "OK"))
    return 1 if warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
