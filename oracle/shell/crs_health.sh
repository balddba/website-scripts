#!/usr/bin/env bash
#===============================================================================
#
# Script Name: crs_health.sh
# Title: CRS health snapshot
# Tags: RAC, Grid
# Purpose: Prints CRS status, resource tree, and voting disks
#
# Description:
#   Quick CRS / HAS health snapshot for a RAC or Restart host. Run as the
#   Grid Infrastructure owner.
#
# Parameters:
#   None.
#
# Required Privileges:
#   - Grid Infrastructure owner
#   - crsctl and oifcfg on PATH
#
# Output Format:
#   - crsctl check crs
#   - crsctl stat res -t
#   - oifcfg getif
#   - crsctl query css votedisk
#
# Example Usage:
#   ./crs_health.sh
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================

set -euo pipefail

# Verify the status of local Grid Infrastructure / CRS daemons
echo "=== crsctl check crs ==="
crsctl check crs || true

# Display the tabular status of all registered cluster resources
echo
echo "=== crsctl stat res -t ==="
crsctl stat res -t || true

# Check configured cluster network interfaces (public and cluster interconnect)
echo
echo "=== oifcfg getif ==="
oifcfg getif || true

# Query the state and location of Cluster Synchronization Services (CSS) voting disks
echo
echo "=== votedisks ==="
crsctl query css votedisk || true
