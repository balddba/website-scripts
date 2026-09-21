/*******************************************************************************
*
* Script Name: blocking_locks.sql
* Title: Blocking locks
* Tags: Locks, Sessions, Performance
* Purpose: Show blocker and waiter sessions, lock type, object, wait time, and SQL ID
*
* Description:
*   Builds a blocking tree from V$SESSION.BLOCKING_SESSION, then lists each
*   waiter with the lock type and request from V$LOCK and the object from
*   DBA_OBJECTS / V$LOCKED_OBJECT. blocking_sessions.sql is the compact
*   GV$SESSION view; this script adds lock type, object, and a session tree.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$SESSION
*   - SELECT on V$LOCK
*   - SELECT on V$LOCKED_OBJECT
*   - SELECT on DBA_OBJECTS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Blocking tree: level, SID, serial, username, event, wait seconds, SQL ID
*   - Waiter detail: blocker and waiter identity, lock type, object, SQL IDs
*
* Example Usage:
*   SQL> @blocking_locks.sql
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

COLUMN tree_sid        FORMAT A18              HEADING 'Tree SID'
COLUMN sid             FORMAT 99999            HEADING 'SID'
COLUMN serial#         FORMAT 99999999         HEADING 'Serial#'
COLUMN username        FORMAT A20              HEADING 'Username'
COLUMN event           FORMAT A32 TRUNC        HEADING 'Event'
COLUMN seconds_in_wait FORMAT 999,999          HEADING 'Wait S'
COLUMN sql_id          FORMAT A13              HEADING 'SQL ID'
COLUMN blocking_session FORMAT 99999           HEADING 'Blk SID'
COLUMN blocker_sid     FORMAT 99999            HEADING 'Blk SID'
COLUMN blocker_serial  FORMAT 99999999         HEADING 'Blk Serial'
COLUMN blocker_user    FORMAT A18              HEADING 'Blocker'
COLUMN blocker_event   FORMAT A28 TRUNC        HEADING 'Blk Event'
COLUMN blocker_sql_id  FORMAT A13              HEADING 'Blk SQL'
COLUMN waiter_sid      FORMAT 99999            HEADING 'Wait SID'
COLUMN waiter_serial   FORMAT 99999999         HEADING 'Wait Serial'
COLUMN waiter_user     FORMAT A18              HEADING 'Waiter'
COLUMN waiter_event    FORMAT A28 TRUNC        HEADING 'Wait Event'
COLUMN waiter_sql_id   FORMAT A13              HEADING 'Wait SQL'
COLUMN lock_type       FORMAT A4               HEADING 'Type'
COLUMN request         FORMAT A16              HEADING 'Requested'
COLUMN object_name     FORMAT A40              HEADING 'Object'

PROMPT
PROMPT === Blocking session tree ===
PROMPT

SELECT
    LPAD(' ', 2 * (LEVEL - 1)) || s.sid AS tree_sid,
    s.sid,
    s.serial#,
    s.username,
    s.event,
    s.seconds_in_wait,
    s.sql_id,
    s.blocking_session
FROM v$session s
WHERE s.blocking_session IS NOT NULL
   OR s.sid IN (
        SELECT w.blocking_session
        FROM v$session w
        WHERE w.blocking_session IS NOT NULL
   )
START WITH s.blocking_session IS NULL
       AND s.sid IN (
            SELECT w.blocking_session
            FROM v$session w
            WHERE w.blocking_session IS NOT NULL
       )
CONNECT BY PRIOR s.sid = s.blocking_session
ORDER SIBLINGS BY s.seconds_in_wait DESC, s.sid;

PROMPT
PROMPT === Blocker / waiter lock details ===
PROMPT

SELECT
    blk.sid AS blocker_sid,
    blk.serial# AS blocker_serial,
    blk.username AS blocker_user,
    blk.event AS blocker_event,
    blk.sql_id AS blocker_sql_id,
    wai.sid AS waiter_sid,
    wai.serial# AS waiter_serial,
    wai.username AS waiter_user,
    wai.event AS waiter_event,
    wai.seconds_in_wait,
    wai.sql_id AS waiter_sql_id,
    wl.type AS lock_type,
    DECODE(
        wl.request,
        0, 'None',
        1, 'Null',
        2, 'Row-S (SS)',
        3, 'Row-X (SX)',
        4, 'Share',
        5, 'S/Row-X (SSX)',
        6, 'Exclusive',
        TO_CHAR(wl.request)
    ) AS request,
    NVL(
        o.owner || '.' || o.object_name,
        lo_obj.owner || '.' || lo_obj.object_name
    ) AS object_name
FROM v$session wai
JOIN v$session blk
  ON blk.sid = wai.blocking_session
LEFT JOIN v$lock wl
  ON wl.sid = wai.sid
 AND wl.request > 0
LEFT JOIN dba_objects o
  ON wl.type IN ('TM', 'TO')
 AND o.object_id = wl.id1
LEFT JOIN v$locked_object lo
  ON lo.session_id = blk.sid
 AND wl.type = 'TX'
 AND lo.xidusn = TRUNC(wl.id1 / 65536)
 AND lo.xidslot = MOD(wl.id1, 65536)
 AND lo.xidsqn = wl.id2
LEFT JOIN dba_objects lo_obj
  ON lo_obj.object_id = lo.object_id
WHERE wai.blocking_session IS NOT NULL
ORDER BY wai.seconds_in_wait DESC, wai.sid;

COLUMN tree_sid CLEAR
COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN username CLEAR
COLUMN event CLEAR
COLUMN seconds_in_wait CLEAR
COLUMN sql_id CLEAR
COLUMN blocking_session CLEAR
COLUMN blocker_sid CLEAR
COLUMN blocker_serial CLEAR
COLUMN blocker_user CLEAR
COLUMN blocker_event CLEAR
COLUMN blocker_sql_id CLEAR
COLUMN waiter_sid CLEAR
COLUMN waiter_serial CLEAR
COLUMN waiter_user CLEAR
COLUMN waiter_event CLEAR
COLUMN waiter_sql_id CLEAR
COLUMN lock_type CLEAR
COLUMN request CLEAR
COLUMN object_name CLEAR

SET FEEDBACK ON
SET VERIFY ON
