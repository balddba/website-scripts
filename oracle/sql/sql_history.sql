/*******************************************************************************
*
* Script Name: sql_history.sql
* Title: SQL Execution History
* Tags: Performance, SQL Tuning, AWR
* Purpose: Historical execution statistics for a SQL_ID across AWR snapshots from dba_hist_sqlstat and dba_hist_snapshot (optional &1 for SQL_ID, defaults to '%').
*
* Description:
*   Queries DBA_HIST_SQLSTAT joined with DBA_HIST_SNAPSHOT to display execution
*   history per snapshot for a specified SQL_ID or pattern. Reports execution
*   counts, total elapsed time, elapsed and CPU time per execution, buffer gets
*   per execution, disk reads per execution, and rows processed across AWR
*   intervals. Requires Oracle Diagnostic Pack licensing.
*
* Parameters:
*   &1 - (Optional) SQL_ID or pattern. Default is '%' (all captured statements).
*
* Required Privileges:
*   - SELECT on DBA_HIST_SQLSTAT
*   - SELECT on DBA_HIST_SNAPSHOT
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Snapshot ID, interval start time, instance ID
*   - SQL ID, plan hash value
*   - Execution count delta, total elapsed seconds
*   - Elapsed seconds per execution, CPU seconds per execution
*   - Buffer gets per execution, disk reads per execution, rows processed
*
* Example Usage:
*   sqlplus user/password@yourdb @sql_history.sql
*   sqlplus user/password@yourdb @sql_history.sql 8zxfktj5s7k8m
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

COLUMN c_sqlid NEW_VALUE p_sqlid NOPRINT
SELECT NVL(NULLIF(TRIM('&1'), ''), '%') AS c_sqlid FROM dual;

COLUMN snap_id         FORMAT 99999999         HEADING 'Snap ID'
COLUMN begin_time      FORMAT A16              HEADING 'Begin Time'
COLUMN inst_id         FORMAT 999              HEADING 'Inst'
COLUMN sql_id          FORMAT A13              HEADING 'SQL ID'
COLUMN plan_hash_value FORMAT 9999999999       HEADING 'Plan Hash'
COLUMN executions      FORMAT 999,999,999      HEADING 'Execs'
COLUMN elapsed_sec     FORMAT 999,999.990      HEADING 'Elapsed S'
COLUMN ela_per_exec    FORMAT 999,990.4000     HEADING 'Ela/Exec'
COLUMN cpu_per_exec    FORMAT 999,990.4000     HEADING 'CPU/Exec'
COLUMN gets_per_exec   FORMAT 999,999,999      HEADING 'Gets/Exec'
COLUMN reads_per_exec  FORMAT 999,999,999      HEADING 'Reads/Exec'
COLUMN rows_processed  FORMAT 999,999,999      HEADING 'Rows'

PROMPT
PROMPT === Historical SQL Execution Statistics (DBA_HIST_SQLSTAT) ===
PROMPT

SELECT
    s.snap_id,
    TO_CHAR(sn.begin_interval_time, 'YYYY-MM-DD HH24:MI') AS begin_time,
    s.instance_number AS inst_id,
    s.sql_id,
    s.plan_hash_value,
    s.executions_delta AS executions,
    ROUND(s.elapsed_time_delta / 1e6, 3) AS elapsed_sec,
    ROUND(s.elapsed_time_delta / NULLIF(s.executions_delta, 0) / 1e6, 4) AS ela_per_exec,
    ROUND(s.cpu_time_delta / NULLIF(s.executions_delta, 0) / 1e6, 4) AS cpu_per_exec,
    ROUND(s.buffer_gets_delta / NULLIF(s.executions_delta, 0), 0) AS gets_per_exec,
    ROUND(s.disk_reads_delta / NULLIF(s.executions_delta, 0), 0) AS reads_per_exec,
    s.rows_processed_delta AS rows_processed
FROM dba_hist_sqlstat s
JOIN dba_hist_snapshot sn
  ON sn.snap_id = s.snap_id
 AND sn.dbid = s.dbid
 AND sn.instance_number = s.instance_number
WHERE s.sql_id LIKE '&&p_sqlid'
  AND s.executions_delta > 0
ORDER BY s.snap_id DESC, s.instance_number, s.sql_id;

COLUMN snap_id CLEAR
COLUMN begin_time CLEAR
COLUMN inst_id CLEAR
COLUMN sql_id CLEAR
COLUMN plan_hash_value CLEAR
COLUMN executions CLEAR
COLUMN elapsed_sec CLEAR
COLUMN ela_per_exec CLEAR
COLUMN cpu_per_exec CLEAR
COLUMN gets_per_exec CLEAR
COLUMN reads_per_exec CLEAR
COLUMN rows_processed CLEAR
COLUMN c_sqlid CLEAR

UNDEFINE p_sqlid
UNDEFINE 1

SET FEEDBACK ON
SET VERIFY ON
