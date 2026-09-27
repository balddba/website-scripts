#!/usr/bin/env bash
#===============================================================================
#
# Script Name: intrinsic_latency.sh
# Title: Redis intrinsic latency baseline
# Tags: Redis, Linux, Latency, Performance
# Purpose: Measures operating-system scheduling latency on a Redis host.
#
# Description:
#   Runs redis-cli intrinsic latency mode for a bounded duration. Run this on
#   the Redis server host so the result reflects the operating system Redis uses.
#
# Parameters:
#   -d, --duration SECONDS - Test duration in seconds (default: 30)
#
# Required Privileges:
#   - Shell access to the Redis host
#   - redis-cli in PATH
#
# Output Format:
#   - redis-cli intrinsic latency samples and summary
#
# Example Usage:
#   ./intrinsic_latency.sh
#   ./intrinsic_latency.sh --duration 60
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================

set -uo pipefail

usage() {
    echo "Usage: $0 [-d|--duration SECONDS]"
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

duration=30
while (($# > 0)); do
    case "$1" in
        -d|--duration)
            (($# >= 2)) || fail "$1 requires a value"
            duration=$2
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            fail "unknown argument: $1"
            ;;
    esac
done

[[ $duration =~ ^[1-9][0-9]*$ ]] || fail "duration must be a positive integer"
command -v redis-cli >/dev/null 2>&1 || fail "redis-cli was not found in PATH"

echo "Running intrinsic latency test for ${duration} seconds on $(hostname)..."
redis-cli --intrinsic-latency "$duration"
