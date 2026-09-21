/*******************************************************************************
*
* Script Name: longops.sql
* Title: Session long operations
* Tags: Performance, Sessions, Longops
* Purpose: Display in-progress sessions from GV$SESSION_LONGOPS with percent complete and ETA
*
* Description:
*   Lists long-running operations that have not finished (sofar < totalwork)
*   from GV$SESSION_LONGOPS. Joins GV$SESSION for username, program, wait
*   event, and SQL ID. Re-run the script to watch progress. Covers every RAC
*   instance. Completed longops remain in the view until they age out and are
*   excluded so the report stays current.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on GV$SESSION_LONGOPS
*   - SELECT on GV$SESSION
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Instance, SID, serial, username, program, SQL ID, and wait event
*   - Operation name, target, units, sofar, total, and percent complete
*   - Elapsed seconds, remaining seconds, and the longops message
*
* Example Usage:
*   SQL> @longops.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 240
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN inst_id     FORMAT 999               HEADING 'Inst'
COLUMN sid         FORMAT 99999             HEADING 'SID'
COLUMN serial#     FORMAT 99999999          HEADING 'Serial#'
COLUMN username    FORMAT A20               HEADING 'Username'
COLUMN program     FORMAT A28 TRUNC         HEADING 'Program'
COLUMN sql_id      FORMAT A13               HEADING 'SQL ID'
COLUMN event       FORMAT A32 TRUNC         HEADING 'Event'
COLUMN opname      FORMAT A28 TRUNC         HEADING 'Operation'
COLUMN target      FORMAT A30 TRUNC         HEADING 'Target'
COLUMN sofar       FORMAT 999,999,999       HEADING 'Sofar'
COLUMN totalwork   FORMAT 999,999,999       HEADING 'Total'
COLUMN units       FORMAT A12 TRUNC         HEADING 'Units'
COLUMN pct_done    FORMAT 990.0             HEADING 'Pct'
COLUMN elapsed_sec FORMAT 999,999           HEADING 'Elapsed'
COLUMN eta_sec     FORMAT 999,999           HEADING 'ETA S'
COLUMN message     FORMAT A60 TRUNC         HEADING 'Message'

PROMPT
PROMPT === In-progress long operations ===
PROMPT

SELECT
    l.inst_id,
    l.sid,
    l.serial#,
    NVL(s.username, l.username) AS username,
    SUBSTR(s.program, 1, 28) AS program,
    NVL(l.sql_id, s.sql_id) AS sql_id,
    s.event,
    l.opname,
    l.target,
    l.sofar,
    l.totalwork,
    l.units,
    ROUND(l.sofar / NULLIF(l.totalwork, 0) * 100, 1) AS pct_done,
    l.elapsed_seconds AS elapsed_sec,
    l.time_remaining AS eta_sec,
    l.message
FROM gv$session_longops l
LEFT JOIN gv$session s
  ON s.inst_id = l.inst_id
 AND s.sid = l.sid
 AND s.serial# = l.serial#
WHERE l.totalwork > 0
  AND l.sofar < l.totalwork
ORDER BY pct_done, l.time_remaining NULLS LAST, l.inst_id, l.sid;

COLUMN inst_id CLEAR
COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN username CLEAR
COLUMN program CLEAR
COLUMN sql_id CLEAR
COLUMN event CLEAR
COLUMN opname CLEAR
COLUMN target CLEAR
COLUMN sofar CLEAR
COLUMN totalwork CLEAR
COLUMN units CLEAR
COLUMN pct_done CLEAR
COLUMN elapsed_sec CLEAR
COLUMN eta_sec CLEAR
COLUMN message CLEAR

SET FEEDBACK ON
SET VERIFY ON
