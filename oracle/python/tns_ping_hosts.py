#!/usr/bin/env python3
# ===============================================================================
#
# Script Name: tns_ping_hosts.py
# Title: tnsnames host inventory
# Tags: Python, TNS
# Purpose: Resolve TNS host:port pairs from a tnsnames.ora-style file and print them
#
# Description:
#   This does not open database sessions. It is a quick inventory of connect
#   endpoints before you run tnsping or a real connection test.
#
# Parameters:
#   argv[1] - (Optional) Path to tnsnames.ora. Default: tnsnames.ora in CWD
#
# Required Privileges:
#   - Read access to the tnsnames file
#
# Output Format:
#   - One line per alias: alias host:port
#
# Example Usage:
#   python tns_ping_hosts.py
#   python tns_ping_hosts.py /etc/tnsnames.ora
#
# Author: Aaron Myers <aaron@balddba.com>
#
# ===============================================================================
"""Resolve TNS host:port pairs from a tnsnames.ora-style file and print them.

This does not open database sessions. It is a quick inventory of connect
endpoints before you run tnsping or a real connection test.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated

import typer

# Regular expressions to extract connection endpoints and aliases from tnsnames.ora content
# Matches the host name or IP address defined in a HOST parameter
HOST_RE = re.compile(r"HOST\s*=\s*([^)\s]+)", re.IGNORECASE)
# Matches the listener port number defined in a PORT parameter
PORT_RE = re.compile(r"PORT\s*=\s*(\d+)", re.IGNORECASE)
# Matches TNS alias definitions anchored at the beginning of lines
ALIAS_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*=", re.MULTILINE)


def parse_tnsnames(text: str) -> list[tuple[str, str, str]]:
    """Return (alias, host, port) tuples from tnsnames content.

    Args:
        text (str): Raw tnsnames.ora text.

    Returns:
        list[tuple[str, str, str]]: Alias, host, and port for each entry found.
    """
    rows: list[tuple[str, str, str]] = []
    # Split the file contents by alias headers into interleaved tokens
    parts = ALIAS_RE.split(text)
    # split yields [preamble, alias, body, alias, body, ...]
    for i in range(1, len(parts), 2):
        alias = parts[i]
        # Retrieve the descriptor body associated with the alias if present
        body = parts[i + 1] if i + 1 < len(parts) else ""
        # Search the descriptor body for host and port parameters
        host_match = HOST_RE.search(body)
        port_match = PORT_RE.search(body)
        # Append valid endpoint records when both host and port are identified
        if host_match and port_match:
            rows.append((alias, host_match.group(1), port_match.group(1)))
    return rows


class TyperApp(typer.Typer):
    """Typer application with parse_args support for programmatic parsing."""

    def parse_args(self, args: Sequence[str] | None = None) -> SimpleNamespace:
        """Parse arguments into a namespace for programmatic use.

        Args:
            args (Sequence[str] | None): Arguments to parse.

        Returns:
            SimpleNamespace: Namespace of parsed arguments.
        """
        cmd = typer.main.get_command(self)
        ctx = cmd.make_context("tns_ping_hosts", list(args) if args is not None else sys.argv[1:])
        return SimpleNamespace(**ctx.params)


app = TyperApp(
    add_completion=False,
    help="Resolve TNS host:port pairs from a tnsnames.ora-style file and print them.",
)


@app.command()
def run(
    path: Annotated[
        Path,
        typer.Argument(
            help="Path to tnsnames.ora file (default: tnsnames.ora in CWD)",
        ),
    ] = Path("tnsnames.ora"),
) -> int:
    """Print alias, host, and port from a tnsnames file.

    Args:
        path (Path): Path to tnsnames.ora file.

    Returns:
        int: Process exit code.
    """
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 1
    for alias, host, port in parse_tnsnames(path.read_text()):
        print(f"{alias:24} {host}:{port}")
    return 0


def build_parser() -> TyperApp:
    """Build and return the CLI argument parser.

    Returns:
        TyperApp: Configured Typer application.
    """
    return app


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the CLI application.

    Args:
        argv (Sequence[str] | None): Optional list of command-line arguments.

    Returns:
        int: Exit status code.
    """
    try:
        if argv is not None:
            args = list(argv[1:]) if len(argv) > 0 and argv[0].endswith(".py") else list(argv)
        else:
            args = None
        ret = app(args=args, standalone_mode=False)
        return 0 if ret is None else int(ret)
    except typer.Exit as exc:
        return exc.exit_code
    except (typer.BadParameter, typer.exceptions.TyperException) as exc:
        sys.exit(getattr(exc, "exit_code", 2))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    app()
