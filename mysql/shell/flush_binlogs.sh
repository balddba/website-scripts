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
#   - mysql client output from FLUSH LOGS
#
# Example Usage:
#   ./flush_binlogs.sh
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================

mysql --login-path=root -e "flush logs;"
