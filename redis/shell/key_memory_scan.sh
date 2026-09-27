#!/usr/bin/env bash
#===============================================================================
#
# Script Name: key_memory_scan.sh
# Title: Redis large-key memory scan
# Tags: Redis, Memory, Big Keys, Troubleshooting
# Purpose: Scans a Redis keyspace for large keys using redis-cli.
#
# Description:
#   Runs redis-cli --bigkeys or --memkeys against the selected Redis URL. Both
#   modes use SCAN, but they still inspect the full keyspace and should be run
#   carefully on busy production servers.
#
# Parameters:
#   MODE - bigkeys or memkeys
#   REDIS_URL - Connection URL (default: redis://localhost:6379/0)
#
# Required Privileges:
#   - redis-cli in PATH
#   - Permission to run SCAN and type-specific size or memory commands
#
# Output Format:
#   - Native redis-cli key sampling and summary output
#
# Example Usage:
#   ./key_memory_scan.sh bigkeys
#   REDIS_URL='rediss://user:password@host:6379/0' ./key_memory_scan.sh memkeys
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================

set -uo pipefail

usage() {
    echo "Usage: $0 {bigkeys|memkeys}"
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

(($# == 1)) || { usage >&2; exit 2; }
mode=$1
[[ $mode == "bigkeys" || $mode == "memkeys" ]] || fail "mode must be bigkeys or memkeys"
command -v redis-cli >/dev/null 2>&1 || fail "redis-cli was not found in PATH"

redis_url=${REDIS_URL:-redis://localhost:6379/0}
echo "WARNING: this performs a full SCAN of the selected Redis database." >&2
redis-cli --uri "$redis_url" "--${mode}"
