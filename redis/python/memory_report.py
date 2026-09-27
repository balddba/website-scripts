#!/usr/bin/env python3
#===============================================================================
#
# Script Name: memory_report.py
# Title: Redis memory and eviction report
# Tags: Redis, Python, Memory, Evictions, OOM
# Purpose: Reports Redis memory pressure, eviction policy, and OOM indicators.
#
# Description:
#   Reads INFO memory and stats, calculates maxmemory utilization, and optionally
#   includes MEMORY DOCTOR advice. Use key_memory_scan.sh to locate large keys.
#
# Parameters:
#   --url URL  Redis URL (default: REDIS_URL or redis://localhost:6379/0)
#   --doctor   Include the MEMORY DOCTOR response
#
# Required Privileges:
#   - Permission to connect, PING, INFO memory/stats, and optionally MEMORY DOCTOR
#   - Python package redis (`python -m pip install redis`)
#
# Output Format:
#   - Memory totals, policy, fragmentation, evictions, and warning status
#
# Example Usage:
#   python memory_report.py --doctor
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
"""Report Redis memory pressure, eviction settings, and OOM indicators."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    parser.add_argument("--doctor", action="store_true", help="include MEMORY DOCTOR advice")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Query Redis and print memory diagnostics."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        import redis
    except ImportError:
        print("ERROR: install redis-py with: python -m pip install redis", file=sys.stderr)
        return 2

    client = redis.Redis.from_url(args.url, decode_responses=True, socket_connect_timeout=2.0, socket_timeout=10.0)
    try:
        memory = client.info("memory")
        stats = client.info("stats")
        doctor = client.execute_command("MEMORY", "DOCTOR") if args.doctor else None
    except redis.RedisError as exc:
        print(f"ERROR: unable to read Redis memory information: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()

    used = int(memory.get("used_memory", 0))
    maximum = int(memory.get("maxmemory", 0))
    utilization = used / maximum if maximum else 0.0
    fragmentation = float(memory.get("mem_fragmentation_ratio", 0.0))
    evicted = int(stats.get("evicted_keys", 0))

    print("Redis Memory Report")
    print("===================")
    print(f"Used memory        : {memory.get('used_memory_human', 'n/a')}")
    print(f"Peak memory        : {memory.get('used_memory_peak_human', 'n/a')}")
    print(f"Maximum memory     : {memory.get('maxmemory_human', 'unlimited') if maximum else 'unlimited'}")
    print(f"Memory utilization : {utilization:.1%}" if maximum else "Memory utilization : n/a (no maxmemory limit)")
    print(f"Eviction policy    : {memory.get('maxmemory_policy', 'n/a')}")
    print(f"Evicted keys       : {evicted}")
    print(f"Fragmentation      : {fragmentation:.2f}")

    warnings = []
    if maximum == 0:
        warnings.append("maxmemory is not configured")
    elif utilization >= 0.8:
        warnings.append("memory utilization is at or above 80%")
    if evicted:
        warnings.append("Redis has evicted keys")
    if fragmentation >= 1.5:
        warnings.append("memory fragmentation is high")
    print("Status              : " + ("WARNING - " + "; ".join(warnings) if warnings else "OK"))

    if doctor is not None:
        print("\nMEMORY DOCTOR")
        print("-------------")
        print(doctor)
    return 1 if warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
