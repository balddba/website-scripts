/*******************************************************************************
*
* Script Name: autoextend_report.sql
* Title: Autoextend report
* Tags: Capacity, Datafiles
* Purpose: Reports auto-extend settings for Oracle tablespaces and their datafiles
*
* Description:
*   This script generates a formatted report showing the auto-extend settings
*   for Oracle database datafiles. It can report on either all tablespaces
*   or a specific tablespace if provided as an argument.
*
* Parameters:
*   &1 - (Optional) Tablespace name to filter results
*        If not provided, script will report on all tablespaces
*
* Required Privileges:
*   - SELECT on DBA_DATA_FILES
*
* Output Format:
*   For each tablespace:
*   - Tablespace name
*   - File name (60 chars)
*   - Size in MB
*   - Auto-extend setting (TRUE/FALSE)
*
* Example Usage:
*   @autoextend_report         -- Report on all tablespaces
*   @autoextend_report USERS   -- Report on USERS tablespace only
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET LINESIZE 200
SET PAGESIZE 100

COLUMN tablespace_name FORMAT A30
COLUMN file_name FORMAT A60
COLUMN size_mb FORMAT 999,999,990.0
COLUMN autoextensible FORMAT A10

SELECT
    tablespace_name,
    file_name,
    ROUND(bytes / 1024 / 1024, 1) AS size_mb,
    autoextensible
FROM dba_data_files
WHERE tablespace_name = NVL(UPPER('&1'), tablespace_name)
ORDER BY tablespace_name, file_name;
