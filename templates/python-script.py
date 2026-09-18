#!/usr/bin/env python3
#===============================================================================
#
# Script Name: script.py
# Title: Script title
# Tags: Python, Admin
# Purpose: One-line description of what this script does
#
# Description:
#   Longer explanation of behavior and when to use this script.
#
# Parameters:
#   argv[1] - (Required) Describe the required argument
#   argv[2] - (Optional) Describe the optional argument
#
# Required Privileges:
#   - Describe the OS user, database account, or files this script needs
#
# Output Format:
#   - Describe stdout, logs, or files this script writes
#
# Example Usage:
#   python script.py required-arg
#   python script.py required-arg optional-arg
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
"""Template Python script for the website-scripts catalog.

Replace this module docstring and main() with the real tool.
"""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    """Run the script.

    Args:
        argv (list[str]): Command-line arguments, including the program name.

    Returns:
        int: Process exit code.
    """
    if len(argv) < 2 or argv[1] in {"-h", "--help"}:
        print("Usage: script.py <required-arg> [optional-arg]", file=sys.stderr)
        return 0 if len(argv) >= 2 else 2

    required_arg = argv[1]
    optional_arg = argv[2] if len(argv) > 2 else ""
    print(f"TODO: replace this template body. required={required_arg} optional={optional_arg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
