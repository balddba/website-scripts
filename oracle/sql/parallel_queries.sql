/*******************************************************************************
*
* Script Name: parallel_queries.sql
* Title: Parallel query sessions
* Tags: Parallel, Performance, Sessions
* Purpose: Show current PX slaves, requested versus actual DOP, QC session, and PQ stats
*
* Description:
*   Lists query coordinators and PX slaves from GV$PX_SESSION joined to
*   GV$SESSION (requested and actual DOP, SQL ID, wait event). GV$PX_PROCESS
*   shows slave process status. GV$PQ_SYSSTAT (and GV$PQ_SLAVE when rows
*   exist) provide instance-level parallel query counters. Covers every RAC
*   instance.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on GV$PX_SESSION
*   - SELECT on GV$PX_PROCESS
*   - SELECT on GV$SESSION
*   - SELECT on GV$PQ_SYSSTAT
*   - SELECT on GV$PQ_SLAVE
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - QC and slave SID, serial, username, SQL ID, requested/actual DOP
*   - PX process name, status, and OS PID
*   - PQ sysstat counters and any currently active PQ slaves
*
* Example Usage:
*   SQL> @parallel_queries.sql
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

COLUMN inst_id      FORMAT 999               HEADING 'Inst'
COLUMN role         FORMAT A6                HEADING 'Role'
COLUMN qcinst_id    FORMAT 999               HEADING 'QC Inst'
COLUMN qcsid        FORMAT 99999             HEADING 'QC SID'
COLUMN qcserial#    FORMAT 99999999          HEADING 'QC Serial'
COLUMN pid          FORMAT 999999            HEADING 'PID'
COLUMN sid          FORMAT 99999             HEADING 'SID'
COLUMN serial#      FORMAT 99999999          HEADING 'Serial#'
COLUMN username     FORMAT A20               HEADING 'Username'
COLUMN sql_id       FORMAT A13               HEADING 'SQL ID'
COLUMN event        FORMAT A32 TRUNC         HEADING 'Event'
COLUMN server_group FORMAT 9999              HEADING 'Grp'
COLUMN server_set   FORMAT 9999              HEADING 'Set'
COLUMN server#      FORMAT 9999              HEADING 'Svr#'
COLUMN req_degree   FORMAT 9999              HEADING 'Req DOP'
COLUMN degree       FORMAT 9999              HEADING 'Act DOP'
COLUMN server_name  FORMAT A12               HEADING 'Slave'
COLUMN status       FORMAT A10               HEADING 'Status'
COLUMN spid         FORMAT A12               HEADING 'OS PID'
COLUMN statistic    FORMAT A40               HEADING 'Statistic'
COLUMN value        FORMAT 999,999,999,999   HEADING 'Value'
COLUMN slave_name   FORMAT A12               HEADING 'Slave'
COLUMN sessions     FORMAT 999,999           HEADING 'Sessions'
COLUMN idle_time_cur FORMAT 999,999          HEADING 'Idle Cur'
COLUMN busy_time_cur FORMAT 999,999          HEADING 'Busy Cur'
COLUMN cpu_secs_cur FORMAT 999,999           HEADING 'CPU Cur'

PROMPT
PROMPT === Current PX sessions (QC and slaves) ===
PROMPT

SELECT
    px.inst_id,
    CASE
        WHEN px.sid = px.qcsid
         AND NVL(px.qcinst_id, px.inst_id) = px.inst_id THEN 'QC'
        ELSE 'SLAVE'
    END AS role,
    px.qcinst_id,
    px.qcsid,
    px.qcserial#,
    px.sid,
    px.serial#,
    s.username,
    s.sql_id,
    s.event,
    px.server_group,
    px.server_set,
    px.server#,
    px.req_degree,
    px.degree
FROM gv$px_session px
JOIN gv$session s
  ON s.inst_id = px.inst_id
 AND s.sid = px.sid
 AND s.serial# = px.serial#
ORDER BY
    px.inst_id,
    px.qcinst_id,
    px.qcsid,
    CASE
        WHEN px.sid = px.qcsid
         AND NVL(px.qcinst_id, px.inst_id) = px.inst_id THEN 0
        ELSE 1
    END,
    px.server_group,
    px.server_set,
    px.server#;

PROMPT
PROMPT === PX processes ===
PROMPT

SELECT
    p.inst_id,
    p.server_name,
    p.status,
    p.pid,
    p.sid,
    s.serial#,
    s.username,
    s.sql_id,
    p.spid
FROM gv$px_process p
LEFT JOIN gv$session s
  ON s.inst_id = p.inst_id
 AND s.sid = p.sid
ORDER BY p.inst_id, p.status, p.server_name;

PROMPT
PROMPT === PQ sysstat ===
PROMPT

SELECT
    inst_id,
    statistic,
    value
FROM gv$pq_sysstat
ORDER BY inst_id, statistic;

PROMPT
PROMPT === PQ slaves (GV$PQ_SLAVE) ===
PROMPT

SELECT
    inst_id,
    slave_name,
    status,
    sessions,
    idle_time_cur,
    busy_time_cur,
    cpu_secs_cur
FROM gv$pq_slave
ORDER BY inst_id, status, slave_name;

COLUMN inst_id CLEAR
COLUMN role CLEAR
COLUMN qcinst_id CLEAR
COLUMN qcsid CLEAR
COLUMN pid CLEAR
COLUMN qcserial# CLEAR
COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN username CLEAR
COLUMN sql_id CLEAR
COLUMN event CLEAR
COLUMN server_group CLEAR
COLUMN server_set CLEAR
COLUMN server# CLEAR
COLUMN req_degree CLEAR
COLUMN degree CLEAR
COLUMN server_name CLEAR
COLUMN status CLEAR
COLUMN spid CLEAR
COLUMN statistic CLEAR
COLUMN value CLEAR
COLUMN slave_name CLEAR
COLUMN sessions CLEAR
COLUMN idle_time_cur CLEAR
COLUMN busy_time_cur CLEAR
COLUMN cpu_secs_cur CLEAR

SET FEEDBACK ON
SET VERIFY ON
