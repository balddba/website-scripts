#!/usr/bin/env bash
#===============================================================================
#
# Script Name: script.sh
# Title: Script title
# Tags: Oracle, Admin
# Purpose: One-line description of what this script does
#
# Description:
#   Longer explanation of behavior and when to use this script.
#
# Parameters:
#   $1 - (Required) Describe the required argument
#   $2 - (Optional) Describe the optional argument
#
# Required Privileges:
#   - Describe the OS user, Oracle account, or files this script needs
#
# Output Format:
#   - Describe stdout, logs, or files this script writes
#
# Example Usage:
#   ./script.sh required-arg
#   ./script.sh required-arg optional-arg
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================

set -uo pipefail

usage() {
  cat <<'EOF'
Usage: script.sh <required-arg> [optional-arg]

Arguments:
  required-arg    Describe the required argument
  optional-arg    Describe the optional argument
EOF
}

fail() {
  printf '%s\n' "$*" >&2
  exit 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 1 ]]; then
  usage >&2
  fail "missing required argument"
fi

REQUIRED_ARG="${1}"
OPTIONAL_ARG="${2:-}"

if [[ -z "${REQUIRED_ARG}" ]]; then
  fail "required-arg must not be empty"
fi

# Validate inputs here before any Oracle / RMAN / database work.
# Example: [[ -r "${ORACLE_HOME}/bin/sqlplus" ]] || fail "sqlplus not found"

printf 'TODO: replace this template body. required=%s optional=%s\n' \
  "${REQUIRED_ARG}" "${OPTIONAL_ARG}"
