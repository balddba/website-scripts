#!/usr/bin/env python3
#===============================================================================
#
# Script Name: cluster_failover.py
# Title: Redis Cluster role switch
# Tags: Redis, Python, Cluster, Failover, High Availability
# Purpose: Promotes a selected Redis Cluster replica and demotes its primary.
#
# Description:
#   Connects directly to the replica that should become primary, validates its
#   role and replication state, and runs CLUSTER FAILOVER. The default dry run
#   prints the proposed operation without changing the cluster. Coordinated mode
#   is safest; force and takeover modes are intended for failure recovery.
#
# Parameters:
#   --url URL            URL of the replica to promote (or REDIS_URL)
#   --mode MODE          coordinated, force, or takeover (default: coordinated)
#   --timeout SECONDS    Promotion verification timeout (default: 30)
#   --execute            Perform the failover; otherwise run preflight only
#   --allow-data-loss    Required with --mode takeover and --execute
#
# Required Privileges:
#   - Permission to connect, PING, INFO replication, and CLUSTER commands
#   - Python package redis (`python -m pip install redis`)
#
# Output Format:
#   - Preflight plan followed by failover and role-verification status
#
# Example Usage:
#   python cluster_failover.py --url redis://replica-01:6379/0
#   python cluster_failover.py --url redis://replica-01:6379/0 --execute
#   python cluster_failover.py --url redis://replica-01:6379/0 --mode force --execute
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
"""Safely promote a selected Redis Cluster replica with CLUSTER FAILOVER."""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit


def positive_integer(value: str) -> int:
    """Validate a positive integer argument."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    env_url = os.getenv("REDIS_URL")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=env_url,
        required=env_url is None,
        help="URL of the replica to promote (or set REDIS_URL)",
    )
    parser.add_argument(
        "--mode",
        choices=("coordinated", "force", "takeover"),
        default="coordinated",
    )
    parser.add_argument("--timeout", type=positive_integer, default=30)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--allow-data-loss",
        action="store_true",
        help="acknowledge consistency and data-loss risk in takeover mode",
    )
    args = parser.parse_args(argv)
    if args.execute and args.mode == "takeover" and not args.allow_data_loss:
        parser.error("--mode takeover with --execute requires --allow-data-loss")
    if args.allow_data_loss and args.mode != "takeover":
        parser.error("--allow-data-loss is valid only with --mode takeover")
    return args


def safe_endpoint(url: str) -> str:
    """Return a Redis endpoint without credentials."""
    parsed = urlsplit(url)
    scheme = parsed.scheme or "redis"
    host = parsed.hostname or "localhost"
    port = parsed.port or (6380 if scheme == "rediss" else 6379)
    return f"{scheme}://{host}:{port}"


def parse_cluster_info(response: Any) -> dict[str, Any]:
    """Normalize a CLUSTER INFO response."""
    if isinstance(response, Mapping):
        return dict(response)
    if isinstance(response, bytes):
        response = response.decode("utf-8", errors="replace")
    info = {}
    for line in str(response).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            info[key] = value
    return info


def enabled(value: Any) -> bool:
    """Interpret Redis boolean-like values."""
    return value in {1, "1", "yes"}


def preflight(info: Mapping[str, Any], cluster: Mapping[str, Any], mode: str) -> list[str]:
    """Validate whether the selected node can be promoted."""
    errors = []
    role = str(info.get("role", "unknown"))
    link = str(info.get("master_link_status", "unknown"))
    if role not in {"slave", "replica"}:
        errors.append(f"target role is {role}; the target must be a replica")
    if enabled(info.get("master_sync_in_progress")):
        errors.append("the replica is still synchronizing with its primary")
    if mode == "coordinated" and link != "up":
        errors.append(f"coordinated failover requires an available primary link; link is {link}")
    if mode in {"coordinated", "force"} and cluster.get("cluster_state") != "ok":
        errors.append(
            f"{mode} failover requires a healthy cluster; state is {cluster.get('cluster_state', 'unknown')}"
        )
    return errors


def command_for(mode: str) -> list[str]:
    """Build the CLUSTER FAILOVER command."""
    command = ["CLUSTER", "FAILOVER"]
    if mode != "coordinated":
        command.append(mode.upper())
    return command


def main(argv: Sequence[str] | None = None) -> int:
    """Validate and optionally execute a Redis Cluster role switch."""
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
        replication = client.info("replication")
        cluster = parse_cluster_info(client.execute_command("CLUSTER", "INFO"))
        node_id = client.execute_command("CLUSTER", "MYID")
    except redis.RedisError as exc:
        print(f"ERROR: preflight failed: {exc}", file=sys.stderr)
        client.close()
        return 1

    print("Redis Cluster Failover Plan")
    print("===========================")
    print(f"Target replica : {safe_endpoint(args.url)}")
    print(f"Target node ID : {node_id}")
    print(f"Current role   : {replication.get('role', 'unknown')}")
    print(f"Current primary: {replication.get('master_host', 'unknown')}:{replication.get('master_port', 'unknown')}")
    print(f"Primary link   : {replication.get('master_link_status', 'unknown')}")
    print(f"Cluster state  : {cluster.get('cluster_state', 'unknown')}")
    print(f"Mode           : {args.mode}")
    print(f"Command        : {' '.join(command_for(args.mode))}")

    errors = preflight(replication, cluster, args.mode)
    if errors:
        print("\nPreflight: FAILED")
        for error in errors:
            print(f"- {error}")
        client.close()
        return 1

    print("\nPreflight: PASSED")
    if not args.execute:
        print("Dry run only. Add --execute to perform this role switch.")
        client.close()
        return 0

    command = command_for(args.mode)
    try:
        response = client.execute_command(*command)
        print(f"Failover request: {response}")
    except redis.RedisError as exc:
        print(f"ERROR: failover request failed: {exc}", file=sys.stderr)
        client.close()
        return 1

    deadline = time.monotonic() + args.timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            replication = client.info("replication")
            if replication.get("role") == "master":
                print("Role verification: target is now the primary")
                client.close()
                return 0
        except redis.RedisError as exc:
            last_error = exc
        time.sleep(0.5)

    client.close()
    detail = f"; last Redis error: {last_error}" if last_error else ""
    print(f"ERROR: target did not become primary within {args.timeout} seconds{detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
