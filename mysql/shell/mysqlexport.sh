#!/usr/bin/env bash
#===============================================================================
#
# Script Name: mysqlexport.sh
# Title: MySQL schema export
# Tags: Backup, Export
# Purpose: Dump non-system MySQL schemas to a timestamped SQL file
#
# Description:
#   Builds a list of schemas excluding mysql, information_schema, sys, and
#   performance_schema, then runs mysqldump. Deletes export files older than
#   three days under /data/exports.
#
# Parameters:
#   None.
#
# Required Privileges:
#   - mysql login-path root
#   - Write access to /data/exports
#
# Output Format:
#   - /data/exports/recapYYYYMMDD_HHMMSS.sql
#
# Example Usage:
#   ./mysqlexport.sh
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================

#-------------------------------------------------------------------------------
#   Local variables defined here
#-------------------------------------------------------------------------------
DATE=`date '+%Y%m%d_%H%M%S'`; # Static date string good for creating unique log files


#-------------------------------------------------------------------------------
#  cleanup section. Delete any exports older than 3 days
#-------------------------------------------------------------------------------
find /data/exports/*.sql -mtime +3 -exec rm {} \;


#-------------------------------------------------------------------------------
#  Generate a list of databases to export non-system databases
#-------------------------------------------------------------------------------
DATABASE_LIST=$(mysql --login-path=root -NBe 'show schemas' | grep -wv 'mysql\|information_schema\|sys\|performance_schema')


#-------------------------------------------------------------------------------
#  dump the databases
#-------------------------------------------------------------------------------
mysqldump --login-path=root --socket=/var/lib/mysql/mysql.sock --databases $DATABASE_LIST --create-options --add-drop-table --add-locks --create-options --extended-insert --quick --routines --disable-keys --dump-date --flush-logs --flush-privileges --single-transaction --result-file=/data/exports/recap${DATE}.sql --verbose