/*******************************************************************************
*
* Script Name: rollback_progress.sql
* Title: Rollback progress
* Tags: Undo, Transactions, Recovery
* Purpose: Monitor in-flight rollbacks, remaining undo, and transaction recovery
*
* Description:
*   Reports sessions and transactions that are rolling back, remaining undo
*   blocks and records, longops percent complete, and SMON/PMON fast-start
*   transaction recovery. BITAND(flag, 128) marks a transaction as rolling
*   back. used_ublk and used_urec fall as rollback proceeds; re-run the
*   script to measure progress when longops or fast-start percent is not
*   published. Covers every RAC instance through GV$ views.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on GV$TRANSACTION
*   - SELECT on GV$SESSION
*   - SELECT on GV$SESSION_LONGOPS
*   - SELECT on GV$FAST_START_TRANSACTIONS
*   - SELECT on GV$FAST_START_SERVERS
*   - SELECT on V$PARAMETER
*   - SELECT on V$SQLCOMMAND
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Transactions currently rolling back, with remaining undo and wait event
*   - Session longops rows for Transaction Rollback (percent and ETA)
*   - Fast-start recovery of dead transactions (percent and ETA)
*   - Fast-start recovery server (parallel rollback slave) status
*
* Example Usage:
*   SQL> @rollback_progress.sql
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

COLUMN c_blk NEW_VALUE p_blksize NOPRINT
SELECT TO_NUMBER(value) AS c_blk
FROM v$parameter
WHERE name = 'db_block_size';

COLUMN inst_id          FORMAT 999               HEADING 'Inst'
COLUMN sid              FORMAT 99999             HEADING 'SID'
COLUMN serial#          FORMAT 99999999          HEADING 'Serial#'
COLUMN username         FORMAT A20               HEADING 'Username'
COLUMN program          FORMAT A28 TRUNC         HEADING 'Program'
COLUMN xid              FORMAT A18               HEADING 'XID'
COLUMN undo_mb          FORMAT 999,999,990.9     HEADING 'Undo MB'
COLUMN used_ublk        FORMAT 999,999,999       HEADING 'Undo Blks'
COLUMN used_urec        FORMAT 999,999,999       HEADING 'Undo Recs'
COLUMN start_time       FORMAT A20               HEADING 'Tx Start'
COLUMN command_name     FORMAT A16 TRUNC         HEADING 'Command'
COLUMN sql_id           FORMAT A13               HEADING 'SQL ID'
COLUMN event            FORMAT A32 TRUNC         HEADING 'Event'
COLUMN wait_sec         FORMAT 999,999           HEADING 'Wait S'
COLUMN opname           FORMAT A28 TRUNC         HEADING 'Operation'
COLUMN sofar            FORMAT 999,999,999       HEADING 'Sofar'
COLUMN totalwork        FORMAT 999,999,999       HEADING 'Total'
COLUMN pct_done         FORMAT 990.0             HEADING 'Pct'
COLUMN elapsed_sec      FORMAT 999,999           HEADING 'Elapsed'
COLUMN eta_sec          FORMAT 999,999           HEADING 'ETA S'
COLUMN message          FORMAT A60 TRUNC         HEADING 'Message'
COLUMN usn              FORMAT 9999              HEADING 'USN'
COLUMN slt              FORMAT 99999             HEADING 'Slot'
COLUMN seq              FORMAT 99999999          HEADING 'Seq'
COLUMN state            FORMAT A18               HEADING 'State'
COLUMN undo_done        FORMAT 999,999,999       HEADING 'Blks Done'
COLUMN undo_total       FORMAT 999,999,999       HEADING 'Blks Total'
COLUMN pid              FORMAT 99999             HEADING 'PID'
COLUMN rcvservers       FORMAT 999               HEADING 'Slaves'
COLUMN cpu_sec          FORMAT 999,999           HEADING 'CPU S'

PROMPT
PROMPT Remaining undo (used_ublk / used_urec) falls as rollback proceeds.
PROMPT Re-run the script to measure progress. Longops and fast-start recovery
PROMPT include percent complete when Oracle publishes it.
PROMPT

PROMPT
PROMPT === Transactions rolling back ===
PROMPT

SELECT
    t.inst_id,
    s.sid,
    s.serial#,
    NVL(s.username, '-') AS username,
    SUBSTR(s.program, 1, 28) AS program,
    t.xidusn || '.' || t.xidslot || '.' || t.xidsqn AS xid,
    ROUND(t.used_ublk * &&p_blksize / 1024 / 1024, 1) AS undo_mb,
    t.used_ublk,
    t.used_urec,
    t.start_time,
    NVL(c.command_name, TO_CHAR(s.command)) AS command_name,
    NVL(s.sql_id, s.prev_sql_id) AS sql_id,
    s.event,
    s.seconds_in_wait AS wait_sec
FROM gv$transaction t
LEFT JOIN gv$session s
  ON s.taddr = t.addr
 AND s.inst_id = t.inst_id
LEFT JOIN v$sqlcommand c
  ON c.command_type = s.command
WHERE BITAND(t.flag, 128) = 128
ORDER BY t.used_ublk DESC, t.inst_id, s.sid;

PROMPT
PROMPT === Rollback longops (percent complete) ===
PROMPT

SELECT
    l.inst_id,
    l.sid,
    l.serial#,
    l.opname,
    l.sofar,
    l.totalwork,
    ROUND(l.sofar / NULLIF(l.totalwork, 0) * 100, 1) AS pct_done,
    l.elapsed_seconds AS elapsed_sec,
    l.time_remaining AS eta_sec,
    l.message
FROM gv$session_longops l
WHERE l.opname LIKE '%Rollback%'
  AND l.totalwork > 0
  AND l.sofar < l.totalwork
ORDER BY pct_done, l.inst_id, l.sid;

PROMPT
PROMPT === Fast-start transaction recovery ===
PROMPT

SELECT
    f.inst_id,
    f.usn,
    f.slt,
    f.seq,
    f.state,
    f.undoblocksdone AS undo_done,
    f.undoblockstotal AS undo_total,
    ROUND(f.undoblocksdone / NULLIF(f.undoblockstotal, 0) * 100, 1) AS pct_done,
    f.cputime AS cpu_sec,
    CASE
        WHEN f.undoblocksdone > 0 AND f.cputime > 0
         AND f.undoblockstotal > f.undoblocksdone
        THEN ROUND(
            (f.undoblockstotal - f.undoblocksdone)
            * (f.cputime / f.undoblocksdone)
        )
    END AS eta_sec,
    f.pid,
    f.rcvservers
FROM gv$fast_start_transactions f
WHERE f.state IN ('RECOVERING', 'TO BE RECOVERED')
ORDER BY pct_done NULLS FIRST, f.inst_id, f.usn, f.slt, f.seq;

PROMPT
PROMPT === Fast-start recovery servers ===
PROMPT

SELECT
    s.inst_id,
    s.pid,
    s.state,
    s.undoblocksdone AS undo_done,
    RAWTOHEX(s.xid) AS xid
FROM gv$fast_start_servers s
ORDER BY s.inst_id, s.pid;

COLUMN inst_id CLEAR
COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN username CLEAR
COLUMN program CLEAR
COLUMN xid CLEAR
COLUMN undo_mb CLEAR
COLUMN used_ublk CLEAR
COLUMN used_urec CLEAR
COLUMN start_time CLEAR
COLUMN command_name CLEAR
COLUMN sql_id CLEAR
COLUMN event CLEAR
COLUMN wait_sec CLEAR
COLUMN opname CLEAR
COLUMN sofar CLEAR
COLUMN totalwork CLEAR
COLUMN pct_done CLEAR
COLUMN elapsed_sec CLEAR
COLUMN eta_sec CLEAR
COLUMN message CLEAR
COLUMN usn CLEAR
COLUMN slt CLEAR
COLUMN seq CLEAR
COLUMN state CLEAR
COLUMN undo_done CLEAR
COLUMN undo_total CLEAR
COLUMN pid CLEAR
COLUMN rcvservers CLEAR
COLUMN cpu_sec CLEAR
COLUMN c_blk CLEAR

SET FEEDBACK ON
SET VERIFY ON
