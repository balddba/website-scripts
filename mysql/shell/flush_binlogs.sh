#!/usr/bin/env bash
#===============================================================================
#
# Script Name: flush_binlogs.sh
# Title: Flush MySQL binary logs
# Tags: Backup, Binlog
# Purpose: Run FLUSH LOGS using the root login-path
#
# Description:
#   Closes and rotates the current binary log so backup or replication jobs
#   can start from a new file.
#
# Parameters:
#   None.
#
# Required Privileges:
#   - mysql login-path root with RELOAD
#
# Output Format:
#   - Confirmation message upon successful log flush
#   - Execution duration in seconds
#
# Example Usage:
#   ./flush_binlogs.sh
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================

set -uo pipefail

usage() {
    cat <<'EOF'
Usage: flush_binlogs.sh [-h|--help]

Flushes and rotates MySQL binary logs using the root login-path.
EOF
}

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

if [[ $# -gt 0 ]]; then
    usage >&2
    fail "unexpected argument: $1"
fi

command -v mysql >/dev/null 2>&1 || fail "mysql client not found in PATH"

start_ns=$(date +%s%N 2>/dev/null || true)
start_sec=$SECONDS

echo "Flushing MySQL binary logs..."

if ! mysql --login-path=root -e "flush logs;"; then
    fail "failed to flush binary logs"
fi

end_ns=$(date +%s%N 2>/dev/null || true)
end_sec=$SECONDS

echo "Binary logs flushed successfully."

if [[ "$start_ns" =~ ^[0-9]{19}$ && "$end_ns" =~ ^[0-9]{19}$ && "$end_ns" -ge "$start_ns" ]]; then
    elapsed_ns=$((end_ns - start_ns))
    elapsed_sec=$((elapsed_ns / 1000000000))
    elapsed_ms=$(((elapsed_ns % 1000000000) / 1000000))
    printf 'Elapsed time: %d.%03ds\n' "$elapsed_sec" "$elapsed_ms"
else
    elapsed_sec=$((end_sec - start_sec))
    printf 'Elapsed time: %ds\n' "$elapsed_sec"
fi
