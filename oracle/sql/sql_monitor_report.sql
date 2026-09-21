/*******************************************************************************
*
* Script Name: sql_monitor_report.sql
* Title: Real-Time SQL Monitor
* Tags: Performance, SQL Monitor
* Purpose: Real-Time SQL Monitoring overview from gv$sql_monitor (status, username, sql_id, elapsed time, cpu time, buffer gets, sql text).
*
* Description:
*   Queries GV$SQL_MONITOR to display an overview of actively monitored and
*   recently completed SQL executions. Includes instance ID, execution status,
*   username, SQL ID, execution start time, elapsed time, CPU time, buffer gets,
*   physical read MB, and SQL text snippet. Requires Oracle Tuning Pack and
*   Diagnostic Pack licensing.
*
* Parameters:
*   &1 - (Optional) SQL_ID or username filter. Default is '%' (all).
*
* Required Privileges:
*   - SELECT on GV$SQL_MONITOR
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Instance ID, key, execution status, username
*   - SQL ID, SQL execution ID, execution start time
*   - Elapsed seconds, CPU seconds
*   - Buffer gets, physical read megabytes
*   - SQL text snippet
*
* Example Usage:
*   sqlplus user/password@yourdb @sql_monitor_report.sql
*   sqlplus user/password@yourdb @sql_monitor_report.sql 8zxfktj5s7k8m
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

COLUMN c_filter NEW_VALUE p_filter NOPRINT
SELECT NVL(NULLIF(TRIM('&1'), ''), '%') AS c_filter FROM dual;

COLUMN inst_id        FORMAT 999              HEADING 'Inst'
COLUMN key            FORMAT 999999999999     HEADING 'Key'
COLUMN status         FORMAT A19              HEADING 'Status'
COLUMN username       FORMAT A15              HEADING 'Username'
COLUMN sql_id         FORMAT A13              HEADING 'SQL ID'
COLUMN sql_exec_id    FORMAT 9999999999       HEADING 'Exec ID'
COLUMN sql_exec_start FORMAT A19              HEADING 'Start Time'
COLUMN elapsed_sec    FORMAT 999,990.99       HEADING 'Elapsed S'
COLUMN cpu_sec        FORMAT 999,990.99       HEADING 'CPU S'
COLUMN buffer_gets    FORMAT 999,999,999,999  HEADING 'Buf Gets'
COLUMN read_mb        FORMAT 999,990.99       HEADING 'Read MB'
COLUMN sql_text       FORMAT A50 TRUNC        HEADING 'SQL Text'

PROMPT
PROMPT === Real-Time SQL Monitoring (GV$SQL_MONITOR) ===
PROMPT

SELECT
    m.inst_id,
    m.key,
    m.status,
    m.username,
    m.sql_id,
    m.sql_exec_id,
    TO_CHAR(m.sql_exec_start, 'YYYY-MM-DD HH24:MI:SS') AS sql_exec_start,
    ROUND(m.elapsed_time / 1e6, 2) AS elapsed_sec,
    ROUND(m.cpu_time / 1e6, 2) AS cpu_sec,
    m.buffer_gets,
    ROUND(m.physical_read_bytes / 1024 / 1024, 2) AS read_mb,
    m.sql_text
FROM gv$sql_monitor m
WHERE (m.sql_id LIKE UPPER('&&p_filter')
   OR UPPER(m.username) LIKE UPPER('&&p_filter')
   OR '&&p_filter' = '%')
ORDER BY m.sql_exec_start DESC NULLS LAST, m.inst_id, m.key DESC;

COLUMN inst_id CLEAR
COLUMN key CLEAR
COLUMN status CLEAR
COLUMN username CLEAR
COLUMN sql_id CLEAR
COLUMN sql_exec_id CLEAR
COLUMN sql_exec_start CLEAR
COLUMN elapsed_sec CLEAR
COLUMN cpu_sec CLEAR
COLUMN buffer_gets CLEAR
COLUMN read_mb CLEAR
COLUMN sql_text CLEAR
COLUMN c_filter CLEAR

UNDEFINE p_filter
UNDEFINE 1

SET FEEDBACK ON
SET VERIFY ON
