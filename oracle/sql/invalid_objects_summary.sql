/*******************************************************************************
*
* Script Name: invalid_objects_summary.sql
* Title: Invalid Objects Summary
* Tags: Schema, Objects, Maintenance
* Purpose: Summarizes count of invalid objects grouped by owner and object type from dba_objects where status = 'INVALID'.
*
* Description:
*   Provides a high-level summary of invalid database objects grouped by owner
*   (schema) and object type. Displays the count of invalid objects per type
*   and computes summary totals per owner and for the entire database. Useful
*   for assessing invalid object counts after deployments, schema migrations,
*   or database maintenance.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on DBA_OBJECTS
*
* Output Format:
*   - Owner (Schema)
*   - Object Type
*   - Invalid Object Count
*   - Subtotals per Owner and Report Grand Total
*
* Example Usage:
*   sqlplus user/password@yourdb @invalid_objects_summary.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 200
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN owner         FORMAT A30            HEADING 'Owner'
COLUMN object_type   FORMAT A30            HEADING 'Object Type'
COLUMN invalid_count FORMAT 999,999,990    HEADING 'Invalid Count'

BREAK ON owner SKIP 1 ON REPORT
COMPUTE SUM OF invalid_count ON owner REPORT

PROMPT
PROMPT === Invalid Objects Summary ===
PROMPT

SELECT
    owner,
    object_type,
    COUNT(*) AS invalid_count
FROM dba_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY owner, invalid_count DESC, object_type;

COLUMN owner CLEAR
COLUMN object_type CLEAR
COLUMN invalid_count CLEAR

CLEAR BREAKS
CLEAR COMPUTES

SET FEEDBACK ON
