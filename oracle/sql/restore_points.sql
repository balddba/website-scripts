/*******************************************************************************
*
* Script Name: restore_points.sql
* Title: Restore points
* Tags: Flashback, Backup
* Purpose: List restore points from V$RESTORE_POINT
*
* Description:
*   Shows every restore point: name, SCN, timestamp, guaranteed flashback
*   flag, storage size, and database incarnation. Guaranteed restore points
*   retain flashback logs until dropped and can fill the FRA. TIME is when
*   the restore point was created; SCN is the flashback target.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$RESTORE_POINT
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Name, SCN, time, guarantee flag, storage size, incarnation
*
* Example Usage:
*   SQL> @restore_points.sql
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

COLUMN name                          FORMAT A40              HEADING 'Name'
COLUMN scn                           FORMAT 999999999999999  HEADING 'SCN'
COLUMN restore_time                  FORMAT A19              HEADING 'Time'
COLUMN guarantee_flashback_database  FORMAT A10              HEADING 'Guaranteed'
COLUMN storage_mb                    FORMAT 999,999,990.0    HEADING 'Storage MB'
COLUMN database_incarnation#         FORMAT 9999990          HEADING 'Incarn'
COLUMN preserved                     FORMAT A10              HEADING 'Preserved'

PROMPT
PROMPT === Restore points ===
PROMPT

SELECT
    name,
    scn,
    TO_CHAR(time, 'YYYY-MM-DD HH24:MI:SS') AS restore_time,
    guarantee_flashback_database,
    ROUND(storage_size / 1024 / 1024, 1) AS storage_mb,
    database_incarnation#,
    preserved
FROM v$restore_point
ORDER BY scn, name;

COLUMN name CLEAR
COLUMN scn CLEAR
COLUMN restore_time CLEAR
COLUMN guarantee_flashback_database CLEAR
COLUMN storage_mb CLEAR
COLUMN database_incarnation# CLEAR
COLUMN preserved CLEAR

SET FEEDBACK ON
SET VERIFY ON
