/*******************************************************************************
*
* Script Name: session_io.sql
* Title: Session I/O
* Tags: Sessions, IO
* Purpose: Report block gets, consistent gets, and physical reads per session
*
* Description:
*   Joins V$SESS_IO to V$SESSION for logical and physical I/O counters:
*   block gets, consistent gets, physical reads, block changes, and consistent
*   changes. User sessions are listed by default, ordered by physical reads.
*   Pass a SID to inspect one session, including background processes.
*   Press Enter at the SQL*Plus prompt if no SID is passed.
*
* Parameters:
*   &1 - (Optional) SID. Default is all user sessions.
*
* Required Privileges:
*   - SELECT on V$SESS_IO
*   - SELECT on V$SESSION
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - SID, serial number, username, program, and status
*   - Block gets, consistent gets, and physical reads
*   - Block changes and consistent changes
*
* Example Usage:
*   SQL> @session_io.sql
*   SQL> @session_io.sql 142
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

COLUMN sid                 FORMAT 99999            HEADING 'SID'
COLUMN serial#             FORMAT 99999999         HEADING 'Serial#'
COLUMN username            FORMAT A20              HEADING 'Username'
COLUMN program             FORMAT A28 TRUNC        HEADING 'Program'
COLUMN status              FORMAT A8               HEADING 'Status'
COLUMN block_gets          FORMAT 999,999,999,999  HEADING 'Block Gets'
COLUMN consistent_gets     FORMAT 999,999,999,999  HEADING 'Cons Gets'
COLUMN physical_reads      FORMAT 999,999,999,999  HEADING 'Phy Reads'
COLUMN block_changes       FORMAT 999,999,999,999  HEADING 'Blk Chg'
COLUMN consistent_changes  FORMAT 999,999,999,999  HEADING 'Cons Chg'

PROMPT
PROMPT === Session I/O ===
PROMPT

SELECT
    s.sid,
    s.serial#,
    s.username,
    s.program,
    s.status,
    io.block_gets,
    io.consistent_gets,
    io.physical_reads,
    io.block_changes,
    io.consistent_changes
FROM v$sess_io io
JOIN v$session s
  ON s.sid = io.sid
WHERE (
        :filter_sid IS NOT NULL
        OR s.type = 'USER'
      )
  AND (:filter_sid IS NULL OR s.sid = :filter_sid)
ORDER BY io.physical_reads DESC, io.consistent_gets DESC, s.sid;

COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN username CLEAR
COLUMN program CLEAR
COLUMN status CLEAR
COLUMN block_gets CLEAR
COLUMN consistent_gets CLEAR
COLUMN physical_reads CLEAR
COLUMN block_changes CLEAR
COLUMN consistent_changes CLEAR

UNDEFINE p_sid
UNDEFINE 1
SET FEEDBACK ON
SET VERIFY ON
