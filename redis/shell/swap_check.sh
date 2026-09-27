#!/usr/bin/env bash
#===============================================================================
#
# Script Name: swap_check.sh
# Title: Redis host swap check
# Tags: Redis, Linux, Swap, Performance
# Purpose: Reports active swap and vm.swappiness on a Redis host.
#
# Description:
#   Performs a read-only host check for swap devices, current swap use, and the
#   vm.swappiness setting. It does not disable swap or modify sysctl settings.
#
# Parameters:
#   None.
#
# Required Privileges:
#   - Linux shell access
#   - Read access to /proc and sysctl
#
# Output Format:
#   - Swap totals, active devices, swappiness, and an OK/WARNING status
#
# Example Usage:
#   ./swap_check.sh
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================

set -uo pipefail

usage() {
    echo "Usage: $0"
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

(($# == 0)) || { usage >&2; exit 2; }
[[ -r /proc/meminfo ]] || fail "this script requires Linux /proc/meminfo"
command -v sysctl >/dev/null 2>&1 || fail "sysctl was not found in PATH"

swap_total_kb=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
swap_free_kb=$(awk '/^SwapFree:/ {print $2}' /proc/meminfo)
swap_used_kb=$((swap_total_kb - swap_free_kb))
swappiness=$(sysctl -n vm.swappiness 2>/dev/null) || fail "cannot read vm.swappiness"

echo "Redis Host Swap Check"
echo "====================="
printf 'Swap total  : %s kB\n' "$swap_total_kb"
printf 'Swap used   : %s kB\n' "$swap_used_kb"
printf 'Swappiness  : %s\n' "$swappiness"
echo "Active swap:"
if command -v swapon >/dev/null 2>&1 && swapon --show --noheadings | grep -q .; then
    swapon --show
else
    echo "  none"
fi

if ((swap_total_kb == 0 && swappiness == 0)); then
    echo "Status       : OK - swap is disabled and vm.swappiness is 0"
elif ((swap_used_kb > 0)); then
    echo "Status       : WARNING - the host is actively using swap"
else
    echo "Status       : WARNING - swap or vm.swappiness is enabled"
fi
