/*******************************************************************************
*
* Script Name: last_sql.sql
* Title: Last SQL for a session
* Tags: Sessions, SQL, Performance
* Purpose: Show the current and previous SQL for a session with cursor execution stats
*
* Description:
*   Joins V$SESSION to V$SQL using SQL_ID / SQL_CHILD_NUMBER for the statement
*   now executing, and PREV_SQL_ID / PREV_CHILD_NUMBER for the last statement
*   that completed. Stats come from the matching child cursor: executions,
*   elapsed and CPU time, buffer gets, disk reads, rows processed, last active
*   time, and plan hash. Defaults to the current session via USERENV SID.
*   Press Enter at the SQL*Plus prompt if no SID is passed.
*
* Parameters:
*   &1 - (Optional) SID. Default is the current session SID.
*
* Required Privileges:
*   - SELECT on V$SESSION
*   - SELECT on V$SQL
*   - SELECT on V$SQLAREA
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - SID, serial number, username, and status
*   - Source (CURRENT or PREVIOUS), SQL ID, child number, and plan hash
*   - Executions, elapsed seconds, CPU seconds, buffer gets, disk reads
*   - Rows processed, last active time, and SQL text
*
* Example Usage:
*   SQL> @last_sql.sql
*   SQL> @last_sql.sql 142
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
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), SYS_CONTEXT('USERENV', 'SID')) AS c_sid
FROM dual;

VARIABLE filter_sid NUMBER

BEGIN
    :filter_sid := TO_NUMBER('&&p_sid');
END;
/

COLUMN sid              FORMAT 99999            HEADING 'SID'
COLUMN serial#          FORMAT 99999999         HEADING 'Serial#'
COLUMN username         FORMAT A20              HEADING 'Username'
COLUMN status           FORMAT A8               HEADING 'Status'
COLUMN sql_source       FORMAT A9               HEADING 'Source'
COLUMN sql_id           FORMAT A13              HEADING 'SQL ID'
COLUMN child_number     FORMAT 9999             HEADING 'Child'
COLUMN plan_hash_value  FORMAT 9999999999       HEADING 'Plan Hash'
COLUMN executions       FORMAT 999,999,999      HEADING 'Execs'
COLUMN elapsed_sec      FORMAT 999,999,990.3    HEADING 'Elapsed S'
COLUMN cpu_sec          FORMAT 999,999,990.3    HEADING 'CPU S'
COLUMN buffer_gets      FORMAT 999,999,999,999  HEADING 'Buf Gets'
COLUMN disk_reads       FORMAT 999,999,999      HEADING 'Disk Rd'
COLUMN rows_processed   FORMAT 999,999,999      HEADING 'Rows'
COLUMN last_active_time FORMAT A19              HEADING 'Last Active'
COLUMN sql_text         FORMAT A60 TRUNC        HEADING 'SQL Text'

PROMPT
PROMPT === Last SQL for SID &&p_sid ===
PROMPT

SELECT
    s.sid,
    s.serial#,
    s.username,
    s.status,
    x.sql_source,
    x.sql_id,
    x.child_number,
    NVL(q.plan_hash_value, a.plan_hash_value) AS plan_hash_value,
    NVL(q.executions, a.executions) AS executions,
    ROUND(NVL(q.elapsed_time, a.elapsed_time) / 1e6, 3) AS elapsed_sec,
    ROUND(NVL(q.cpu_time, a.cpu_time) / 1e6, 3) AS cpu_sec,
    NVL(q.buffer_gets, a.buffer_gets) AS buffer_gets,
    NVL(q.disk_reads, a.disk_reads) AS disk_reads,
    NVL(q.rows_processed, a.rows_processed) AS rows_processed,
    NVL(q.last_active_time, a.last_active_time) AS last_active_time,
    NVL(q.sql_text, a.sql_text) AS sql_text
FROM v$session s
JOIN (
    SELECT
        sid,
        'CURRENT' AS sql_source,
        sql_id,
        sql_child_number AS child_number
    FROM v$session
    WHERE sid = :filter_sid
      AND sql_id IS NOT NULL
    UNION ALL
    SELECT
        sid,
        'PREVIOUS' AS sql_source,
        prev_sql_id AS sql_id,
        prev_child_number AS child_number
    FROM v$session
    WHERE sid = :filter_sid
      AND prev_sql_id IS NOT NULL
) x
  ON x.sid = s.sid
LEFT JOIN v$sql q
  ON q.sql_id = x.sql_id
 AND q.child_number = NVL(x.child_number, 0)
LEFT JOIN v$sqlarea a
  ON a.sql_id = x.sql_id
WHERE s.sid = :filter_sid
ORDER BY DECODE(x.sql_source, 'CURRENT', 1, 2), x.child_number;

COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN username CLEAR
COLUMN status CLEAR
COLUMN sql_source CLEAR
COLUMN sql_id CLEAR
COLUMN child_number CLEAR
COLUMN plan_hash_value CLEAR
COLUMN executions CLEAR
COLUMN elapsed_sec CLEAR
COLUMN cpu_sec CLEAR
COLUMN buffer_gets CLEAR
COLUMN disk_reads CLEAR
COLUMN rows_processed CLEAR
COLUMN last_active_time CLEAR
COLUMN sql_text CLEAR

UNDEFINE p_sid
UNDEFINE 1
SET FEEDBACK ON
SET VERIFY ON
