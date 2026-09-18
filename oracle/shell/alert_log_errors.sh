#!/usr/bin/env bash
#===============================================================================
#
# Script Name: alert_log_errors.sh
# Title: Alert log error filter
# Tags: Diagnostics, Alert Log
# Purpose: Tail the last N lines of an Oracle alert log and keep ORA- / error lines
#
# Description:
#   Reads the specified alert log, takes the trailing line count, and greps
#   for ORA-, error, Corrupt, and Hung patterns.
#
# Parameters:
#   $1 - (Required) Path to the Oracle alert log
#   $2 - (Optional) Number of trailing lines to inspect. Default: 2000
#
# Required Privileges:
#   - Read access to the alert log file
#
# Output Format:
#   - Matching alert log lines on stdout
#
# Example Usage:
#   ./alert_log_errors.sh /u01/app/oracle/diag/rdbms/orcl/orcl/trace/alert_orcl.log
#   ./alert_log_errors.sh /u01/app/oracle/diag/rdbms/orcl/orcl/trace/alert_orcl.log 5000
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================

set -euo pipefail

# Path to the Oracle alert log (required positional argument)
ALERT_LOG="${1:?alert log path required}"
# Number of trailing lines to inspect (defaults to 2000 lines)
LINES="${2:-2000}"

# Verify that the specified alert log file exists before proceeding
if [[ ! -f "$ALERT_LOG" ]]; then
  echo "File not found: $ALERT_LOG" >&2
  exit 1
fi

# Extract the last N lines and filter for critical Oracle errors and alert patterns
tail -n "$LINES" "$ALERT_LOG" | grep -E 'ORA-|error|ERROR|Corrupt|Hung' || true
