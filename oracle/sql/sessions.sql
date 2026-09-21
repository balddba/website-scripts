/*******************************************************************************
*
* Script Name: sessions.sql
* Title: Current sessions
* Tags: Sessions, Connections
* Purpose: List current user sessions with SID, serial number, OS process ID, username, machine, and status
*
* Description:
*   Reports every user session from GV$SESSION and the matching OS process ID
*   from GV$PROCESS. Background processes are omitted. STATUS is typically
*   ACTIVE or INACTIVE; KILLED, SNIPED, and CACHED also appear. Covers every
*   RAC instance. Use SID and serial# together for ALTER SYSTEM KILL SESSION.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on GV$SESSION
*   - SELECT on GV$PROCESS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Instance, SID, serial number, and OS process ID
*   - Username, client machine, and session status
*
* Example Usage:
*   SQL> @sessions.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 160
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN inst_id  FORMAT 999               HEADING 'Inst'
COLUMN sid      FORMAT 99999             HEADING 'SID'
COLUMN serial#  FORMAT 99999999          HEADING 'Serial#'
COLUMN os_pid   FORMAT A12               HEADING 'OS PID'
COLUMN username FORMAT A30               HEADING 'Username'
COLUMN machine  FORMAT A40 TRUNC         HEADING 'Machine'
COLUMN status   FORMAT A8                HEADING 'Status'

PROMPT
PROMPT === Current sessions ===
PROMPT

SELECT
    s.inst_id,
    s.sid,
    s.serial#,
    p.spid AS os_pid,
    s.username,
    s.machine,
    s.status
FROM gv$session s
LEFT JOIN gv$process p
  ON p.inst_id = s.inst_id
 AND p.addr = s.paddr
WHERE s.type = 'USER'
ORDER BY
    DECODE(s.status, 'ACTIVE', 1, 'INACTIVE', 2, 3),
    s.username,
    s.inst_id,
    s.sid;

COLUMN inst_id CLEAR
COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN os_pid CLEAR
COLUMN username CLEAR
COLUMN machine CLEAR
COLUMN status CLEAR

SET FEEDBACK ON
SET VERIFY ON
