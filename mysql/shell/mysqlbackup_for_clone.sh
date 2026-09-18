#!/usr/bin/env bash
#===============================================================================
#
# Script Name: mysqlbackup_for_clone.sh
# Title: MySQL backup for clone
# Tags: Backup, Clone
# Purpose: Create a compressed MySQL Enterprise Backup image and tar the backup directory
#
# Description:
#   Runs a compressed mysqlbackup backup-to-image, then tars the resulting
#   backup directory for clone or copy use.
#
# Parameters:
#   None.
#
# Required Privileges:
#   - mysqlbackup with login-path backup
#   - Write access to /mysqldata/backups
#
# Output Format:
#   - Compressed .mbi backup image
#   - Tar archive of the backup directory
#   - Prints backuptar:<file>.tar
#
# Example Usage:
#   ./mysqlbackup_for_clone.sh
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================

#-------------------------------------------------------------------------------
#   Local variables defined here
#-------------------------------------------------------------------------------
DATE=`date '+%Y%m%d_%H%M%S'`; # Static date string good for creating unique log files
BACKUPNAME=redcap_${DATE}.mbi

#-------------------------------------------------------------------------------
#  cleanup section. Delete any exports older than 2 days
#-------------------------------------------------------------------------------
#find /mysqldata/backups/ -maxdepth 1 -mtime +2 -exec rm -rf {} \;

#-------------------------------------------------------------------------------
#  backup the database
#-------------------------------------------------------------------------------
mysqlbackup --login-path=backup --with-timestamp --backup-dir=/mysqldata/backups/ --socket=/mysqldata/datafiles/mysql.sock \
   --compress --backup-image=${BACKUPNAME} backup-to-image

backupdir=$(find /mysqldata/backups/ -name *.mbi | sed 's/\/${BACKUPNAME}//' | sed 's/\/mysqldata\/backups\///')

cd /mysqldata/backups/

tar -cf ${backupdir}.tar ${backupdir}

echo backuptar:${backupdir}.tar