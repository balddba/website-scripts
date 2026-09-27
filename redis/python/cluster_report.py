#!/usr/bin/env python3
#===============================================================================
#
# Script Name: cluster_report.py
# Title: Redis Cluster information
# Tags: Redis, Python, Cluster, High Availability
# Purpose: Displays Redis Cluster health, slot coverage, nodes, roles, and links.
#
# Description:
#   Connects to one Redis Cluster node and reads CLUSTER INFO and CLUSTER NODES.
#   The report highlights incomplete slot coverage, failed or suspected nodes,
#   disconnected links, node roles, primary relationships, and assigned slots.
#
# Parameters:
#   --url URL  Seed-node URL (default: REDIS_URL or redis://localhost:6379/0)
#
# Required Privileges:
#   - Permission to connect, PING, CLUSTER INFO, and CLUSTER NODES
#   - Python package redis (`python -m pip install redis`)
#
# Output Format:
#   - Human-readable cluster health summary and one block per known node
#
# Example Usage:
#   python cluster_report.py --url redis://cluster-node-01.example.com:6379/0
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
"""Display Redis Cluster health, slot coverage, topology, and node state."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from typing import Any


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    return parser.parse_args(argv)


def parse_info(response: Any) -> dict[str, Any]:
    """Normalize a CLUSTER INFO response."""
    if isinstance(response, Mapping):
        return dict(response)
    if isinstance(response, bytes):
        response = response.decode("utf-8", errors="replace")

    result: dict[str, Any] = {}
    for line in str(response).splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        result[key] = int(value) if value.isdigit() else value
    return result


def flag_set(value: Any) -> set[str]:
    """Normalize node flags."""
    if isinstance(value, str):
        return set(value.split(","))
    if isinstance(value, Sequence):
        return {str(flag) for flag in value}
    return set()


def slot_text(value: Any) -> str:
    """Normalize slot assignments for display."""
    if not value:
        return "none"
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return ", ".join(f"{start}-{end}" for start, end in value.items())
    if isinstance(value, Sequence):
        parts = []
        for item in value:
            if isinstance(item, Sequence) and not isinstance(item, str) and len(item) == 2:
                parts.append(f"{item[0]}-{item[1]}")
            else:
                parts.append(str(item))
        return ", ".join(parts)
    return str(value)


def parse_raw_nodes(response: str) -> list[dict[str, Any]]:
    """Parse the text form of CLUSTER NODES."""
    nodes = []
    for line in response.splitlines():
        fields = line.split()
        if len(fields) < 8:
            continue
        nodes.append(
            {
                "id": fields[0],
                "address": fields[1],
                "flags": flag_set(fields[2]),
                "primary": fields[3],
                "ping_sent": fields[4],
                "pong_received": fields[5],
                "epoch": fields[6],
                "link_state": fields[7],
                "slots": " ".join(fields[8:]) or "none",
            }
        )
    return nodes


def parse_nodes(response: Any) -> list[dict[str, Any]]:
    """Normalize raw and redis-py parsed CLUSTER NODES responses."""
    if isinstance(response, bytes):
        return parse_raw_nodes(response.decode("utf-8", errors="replace"))
    if isinstance(response, str):
        return parse_raw_nodes(response)

    nodes = []
    if not isinstance(response, Mapping):
        return nodes
    for identity, details in response.items():
        if not isinstance(details, Mapping):
            continue
        flags = flag_set(details.get("flags", details.get("flag", "")))
        connected = details.get("connected", details.get("link_state", "unknown"))
        if isinstance(connected, bool):
            connected = "connected" if connected else "disconnected"
        nodes.append(
            {
                "id": details.get("node_id", details.get("id", identity)),
                "address": details.get("address", details.get("host", identity)),
                "flags": flags,
                "primary": details.get("master_id", details.get("primary", "-")),
                "ping_sent": details.get("last_ping_sent", details.get("ping_sent", "n/a")),
                "pong_received": details.get("last_pong_rcvd", details.get("pong_received", "n/a")),
                "epoch": details.get("epoch", details.get("config_epoch", "n/a")),
                "link_state": connected,
                "slots": slot_text(details.get("slots")),
            }
        )
    return nodes


def node_role(flags: set[str]) -> str:
    """Return a user-facing node role."""
    if flags & {"master", "primary"}:
        return "primary"
    if flags & {"slave", "replica"}:
        return "replica"
    return "unknown"


def print_nodes(nodes: Sequence[Mapping[str, Any]]) -> list[str]:
    """Print known nodes and return health warnings."""
    warnings = []
    print("\nNodes")
    print("-----")
    for node in nodes:
        flags = flag_set(node.get("flags"))
        role = node_role(flags)
        link_state = str(node.get("link_state", "unknown"))
        marker = " (this node)" if "myself" in flags else ""
        print(f"{node.get('address', 'unknown')}{marker}")
        print(f"  ID           : {node.get('id', 'unknown')}")
        print(f"  Role         : {role}")
        print(f"  Primary ID   : {node.get('primary', '-')}")
        print(f"  Link         : {link_state}")
        print(f"  Config epoch : {node.get('epoch', 'n/a')}")
        print(f"  Slots        : {node.get('slots', 'none')}")
        print(f"  Flags        : {', '.join(sorted(flags)) or 'none'}")

        failure_flags = flags & {"fail", "fail?", "handshake", "noaddr"}
        if failure_flags:
            warnings.append(f"{node.get('address')} has flags {','.join(sorted(failure_flags))}")
        if link_state not in {"connected", "up"}:
            warnings.append(f"{node.get('address')} link is {link_state}")
    return warnings


def main(argv: Sequence[str] | None = None) -> int:
    """Query Redis and print cluster information."""
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
        cluster_info = parse_info(client.execute_command("CLUSTER", "INFO"))
        nodes = parse_nodes(client.execute_command("CLUSTER", "NODES"))
    except redis.RedisError as exc:
        print(f"ERROR: unable to read Redis Cluster information: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()

    state = str(cluster_info.get("cluster_state", "unknown"))
    assigned = int(cluster_info.get("cluster_slots_assigned", 0))
    slots_ok = int(cluster_info.get("cluster_slots_ok", 0))
    slots_pfail = int(cluster_info.get("cluster_slots_pfail", 0))
    slots_fail = int(cluster_info.get("cluster_slots_fail", 0))

    print("Redis Cluster Information")
    print("=========================")
    print(f"State             : {state}")
    print(f"Slots assigned    : {assigned} / 16384")
    print(f"Slots OK          : {slots_ok}")
    print(f"Slots PFAIL       : {slots_pfail}")
    print(f"Slots FAIL        : {slots_fail}")
    print(f"Known nodes       : {cluster_info.get('cluster_known_nodes', len(nodes))}")
    print(f"Primary shards    : {cluster_info.get('cluster_size', 'n/a')}")
    print(f"Current epoch     : {cluster_info.get('cluster_current_epoch', 'n/a')}")
    print(f"Messages sent     : {cluster_info.get('cluster_stats_messages_sent', 'n/a')}")
    print(f"Messages received : {cluster_info.get('cluster_stats_messages_received', 'n/a')}")

    warnings = print_nodes(nodes)
    if state != "ok":
        warnings.append(f"cluster state is {state}")
    if assigned != 16384:
        warnings.append(f"only {assigned} of 16384 slots are assigned")
    if slots_pfail:
        warnings.append(f"{slots_pfail} slots are in PFAIL")
    if slots_fail:
        warnings.append(f"{slots_fail} slots are in FAIL")
    if not nodes:
        warnings.append("no cluster nodes were returned")

    print("\nStatus: " + ("WARNING - " + "; ".join(warnings) if warnings else "OK"))
    return 1 if warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
