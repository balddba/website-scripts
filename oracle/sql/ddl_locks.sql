/*******************************************************************************
*
* Script Name: ddl_locks.sql
* Title: DDL locks
* Tags: Locks, DDL
* Purpose: Show current DDL locks with owning session details
*
* Description:
*   Reports DDL locks from DBA_DDL_LOCKS and joins them to V$SESSION so the
*   lock holder or waiter can be identified by SID, serial number, username,
*   machine, program, module, and SQL ID. Requested lock modes indicate sessions
*   waiting for a DDL lock.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on DBA_DDL_LOCKS
*   - SELECT on V$SESSION
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Object owner, name, and type
*   - Lock mode held and requested
*   - SID, serial number, username, machine, program, module, and SQL ID
*
* Example Usage:
*   SQL> @ddl_locks.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET LINESIZE 240
SET PAGESIZE 100
SET VERIFY OFF

COLUMN owner          FORMAT A24 HEADING 'Owner'
COLUMN object_name    FORMAT A36 HEADING 'Object Name'
COLUMN object_type    FORMAT A18 HEADING 'Object Type'
COLUMN mode_held      FORMAT A14 HEADING 'Held'
COLUMN mode_requested FORMAT A14 HEADING 'Requested'
COLUMN sid            FORMAT 999999 HEADING 'SID'
COLUMN serial#        FORMAT 999999 HEADING 'Serial#'
COLUMN username       FORMAT A20 HEADING 'Username'
COLUMN machine        FORMAT A30 HEADING 'Machine'
COLUMN program        FORMAT A35 HEADING 'Program'
COLUMN module         FORMAT A30 HEADING 'Module'
COLUMN sql_id         FORMAT A13 HEADING 'SQL ID'

PROMPT
PROMPT === Current DDL locks ===
PROMPT

SELECT
    l.owner,
    l.name AS object_name,
    l.type AS object_type,
    l.mode_held,
    l.mode_requested,
    s.sid,
    s.serial#,
    s.username,
    SUBSTR(s.machine, 1, 30) AS machine,
    SUBSTR(s.program, 1, 35) AS program,
    SUBSTR(s.module, 1, 30) AS module,
    s.sql_id
FROM dba_ddl_locks l
LEFT JOIN v$session s
  ON s.sid = l.session_id
ORDER BY
    CASE
        WHEN l.mode_requested <> 'None' THEN 0
        ELSE 1
    END,
    l.owner,
    l.name,
    l.session_id;
