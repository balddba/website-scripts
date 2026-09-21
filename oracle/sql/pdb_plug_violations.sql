/*******************************************************************************
*
* Script Name: pdb_plug_violations.sql
* Title: PDB Plug-in Violations
* Tags: Multitenant, PDB, Maintenance
* Purpose: Inspects outstanding plug-in violations, errors, and warnings from pdb_plug_in_violations or cdb_pdb_plug_in_violations.
*
* Description:
*   Queries CDB_PDB_PLUG_IN_VIOLATIONS to display plug-in violations,
*   compatibility checks, errors, and warnings across pluggable databases.
*   Shows timestamps, violation types, status (such as PENDING or RESOLVED),
*   error messages, and recommended actions.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on CDB_PDB_PLUG_IN_VIOLATIONS (or PDB_PLUG_IN_VIOLATIONS)
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Con ID and PDB Name
*   - Violation Time
*   - Type (ERROR / WARNING)
*   - Status (PENDING / RESOLVED)
*   - Error Number and Cause
*   - Violation Message and Action
*
* Example Usage:
*   sqlplus user/password@yourdb @pdb_plug_violations.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET LINESIZE 200
SET PAGESIZE 100
SET VERIFY OFF
SET FEEDBACK OFF

COLUMN con_id       FORMAT 9990         HEADING 'Con ID'
COLUMN name         FORMAT A25          HEADING 'PDB Name'
COLUMN time_str     FORMAT A19          HEADING 'Violation Time'
COLUMN type         FORMAT A10          HEADING 'Type'
COLUMN status       FORMAT A10          HEADING 'Status'
COLUMN error_number FORMAT 999990       HEADING 'Err#'
COLUMN cause        FORMAT A20          HEADING 'Cause'
COLUMN message      FORMAT A50          HEADING 'Message'
COLUMN action       FORMAT A40          HEADING 'Action'

SELECT
    con_id,
    name,
    TO_CHAR(time, 'YYYY-MM-DD HH24:MI:SS') AS time_str,
    type,
    status,
    error_number,
    cause,
    message,
    action
FROM cdb_pdb_plug_in_violations
ORDER BY
    time DESC,
    con_id,
    name;

COLUMN con_id CLEAR
COLUMN name CLEAR
COLUMN time_str CLEAR
COLUMN type CLEAR
COLUMN status CLEAR
COLUMN error_number CLEAR
COLUMN cause CLEAR
COLUMN message CLEAR
COLUMN action CLEAR

SET FEEDBACK ON
SET VERIFY ON
