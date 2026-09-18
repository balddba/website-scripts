#!/usr/bin/env bash
#===============================================================================
#
# Script Name: mysqlbackup.sh
# Title: MySQL Enterprise Backup
# Tags: Backup, MySQL
# Purpose: Take a full MySQL Enterprise Backup image and prune old backup directories
#
# Description:
#   Runs mysqlbackup backup-to-image into a host-specific directory, removes
#   backup directories older than 14 days, and appends start/end times to
#   timing.log in the newest backup directory.
#
# Parameters:
#   None.
#
# Required Privileges:
#   - mysqlbackup with login-path root
#   - Write access to /mnt/boostfs/mysql/$(hostname)
#
# Output Format:
#   - Backup image redcap.mbi under the timestamped backup directory
#   - timing.log with begin and end timestamps
#
# Example Usage:
#   ./mysqlbackup.sh
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================

#-------------------------------------------------------------------------------
#   Local variables defined here
#-------------------------------------------------------------------------------
STARTDATE=`date '+%Y%m%d_%H%M%S'`; # Static date string good for creating unique log files
BACKUP_DEST=/mnt/boostfs/mysql/$(hostname)
#BACKUP_DEST=/tmp/backup
#-------------------------------------------------------------------------------
#  cleanup section. Delete any exports older than 2 days
#-------------------------------------------------------------------------------
find ${BACKUP_DEST} -maxdepth 1 -mtime +14 -exec rm -rf {} \;


#-------------------------------------------------------------------------------
#  backup the database
#-------------------------------------------------------------------------------
mysqlbackup --login-path=root --with-timestamp --backup-dir=${BACKUP_DEST} --socket=/var/lib/mysql/mysql.sock \
   --backup-image=redcap.mbi backup-to-image

ENDDATE=`date '+%Y%m%d_%H%M%S'`;

#-------------------------------------------------------------------------------
# log the start/stop time for the backup
#-------------------------------------------------------------------------------
LASTDIR=$(find ${BACKUP_DEST} -maxdepth 1 -type d -mmin -2000 | tail -n 1)
LOGFILE=${LASTDIR}/timing.log

echo "begin: ${STARTDATE}" >> ${LOGFILE}
echo "end: ${ENDDATE}" >> ${LOGFILE}