/*******************************************************************************
*
* Script Name: locks.sql
* Title: Database locks
* Tags: Locks, Sessions
* Purpose: List current enqueue locks with session, mode, object, and blocker flag
*
* Description:
*   Reports TM, TX, and UL locks from V$LOCK joined to V$SESSION. TM locks
*   resolve the object via DBA_OBJECTS (ID1 is the object ID). TX locks join
*   V$LOCKED_OBJECT when a row is present. LMODE is the mode held; REQUEST is
*   the mode waited for. BLOCK is 1 when this lock blocks another session.
*   ddl_locks.sql covers DDL locks only; this script is the broader enqueue
*   picture. Press Enter at the SQL*Plus prompt if no SID is passed.
*
* Parameters:
*   &1 - (Optional) SID. Default is all sessions with TM/TX/UL locks.
*
* Required Privileges:
*   - SELECT on V$LOCK
*   - SELECT on V$SESSION
*   - SELECT on V$LOCKED_OBJECT
*   - SELECT on DBA_OBJECTS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - SID, serial number, username, and program
*   - Lock type, mode held, mode requested, ID1, ID2, and hold time
*   - Blocker flag and locked object
*
* Example Usage:
*   SQL> @locks.sql
*   SQL> @locks.sql 142
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

COLUMN c_sid NEW_VALUE p_sid NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), 'ALL') AS c_sid FROM dual;

VARIABLE filter_sid NUMBER

BEGIN
    IF '&&p_sid' = 'ALL' THEN
        :filter_sid := NULL;
    ELSE
        :filter_sid := TO_NUMBER('&&p_sid');
    END IF;
END;
/

COLUMN sid          FORMAT 99999     HEADING 'SID'
COLUMN serial#      FORMAT 99999999  HEADING 'Serial#'
COLUMN username     FORMAT A20       HEADING 'Username'
COLUMN program      FORMAT A24 TRUNC HEADING 'Program'
COLUMN type         FORMAT A4        HEADING 'Type'
COLUMN lmode        FORMAT A16       HEADING 'Held'
COLUMN request      FORMAT A16       HEADING 'Requested'
COLUMN id1          FORMAT 9999999999 HEADING 'ID1'
COLUMN id2          FORMAT 9999999999 HEADING 'ID2'
COLUMN ctime        FORMAT 999,999   HEADING 'Secs'
COLUMN blocker      FORMAT A8        HEADING 'Blocker'
COLUMN object_name  FORMAT A44       HEADING 'Object'

PROMPT
PROMPT === Database locks (TM / TX / UL) ===
PROMPT

SELECT
    s.sid,
    s.serial#,
    s.username,
    s.program,
    l.type,
    DECODE(
        l.lmode,
        0, 'None',
        1, 'Null',
        2, 'Row-S (SS)',
        3, 'Row-X (SX)',
        4, 'Share',
        5, 'S/Row-X (SSX)',
        6, 'Exclusive',
        TO_CHAR(l.lmode)
    ) AS lmode,
    DECODE(
        l.request,
        0, 'None',
        1, 'Null',
        2, 'Row-S (SS)',
        3, 'Row-X (SX)',
        4, 'Share',
        5, 'S/Row-X (SSX)',
        6, 'Exclusive',
        TO_CHAR(l.request)
    ) AS request,
    l.id1,
    l.id2,
    l.ctime,
    DECODE(l.block, 0, 'No', 1, 'Yes', 2, 'Global', TO_CHAR(l.block)) AS blocker,
    NVL(
        o.owner || '.' || o.object_name,
        lo_obj.owner || '.' || lo_obj.object_name
    ) AS object_name
FROM v$lock l
JOIN v$session s
  ON s.sid = l.sid
LEFT JOIN dba_objects o
  ON l.type IN ('TM', 'TO')
 AND o.object_id = l.id1
LEFT JOIN v$locked_object lo
  ON lo.session_id = l.sid
 AND l.type = 'TX'
 AND lo.xidusn = TRUNC(l.id1 / 65536)
 AND lo.xidslot = MOD(l.id1, 65536)
 AND lo.xidsqn = l.id2
LEFT JOIN dba_objects lo_obj
  ON lo_obj.object_id = lo.object_id
WHERE l.type IN ('TM', 'TX', 'UL')
  AND (:filter_sid IS NULL OR s.sid = :filter_sid)
ORDER BY
    DECODE(l.block, 1, 0, 2, 1, 2),
    DECODE(l.request, 0, 1, 0),
    l.ctime DESC,
    s.sid,
    l.type;

COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN username CLEAR
COLUMN program CLEAR
COLUMN type CLEAR
COLUMN lmode CLEAR
COLUMN request CLEAR
COLUMN id1 CLEAR
COLUMN id2 CLEAR
COLUMN ctime CLEAR
COLUMN blocker CLEAR
COLUMN object_name CLEAR

UNDEFINE p_sid
UNDEFINE 1
SET FEEDBACK ON
SET VERIFY ON
