/*******************************************************************************
*
* Script Name: sql_baselines.sql
* Title: SQL Plan Baselines
* Tags: Performance, SPM, Baselines
* Purpose: Lists SQL Plan Baselines from dba_sql_plan_baselines with enabled, accepted, fixed, and reproduced status.
*
* Description:
*   Queries DBA_SQL_PLAN_BASELINES to display SQL Management Base (SMB) plan
*   baselines. Shows SQL handle, plan name, creator, origin, status flags
*   (enabled, accepted, fixed, reproduced, autopurge), execution statistics,
*   timestamps, and SQL text snippet. Filter by handle, plan name, or SQL text.
*
* Parameters:
*   &1 - (Optional) SQL handle, plan name, or text filter. Default is '%' (all).
*
* Required Privileges:
*   - SELECT on DBA_SQL_PLAN_BASELINES
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - SQL handle, plan name, creator, origin
*   - Status flags: enabled, accepted, fixed, reproduced, autopurge
*   - Execution stats: execution count, elapsed time per exec, CPU per exec, buffer gets
*   - Creation and execution timestamps
*   - SQL text snippet
*
* Example Usage:
*   sqlplus user/password@yourdb @sql_baselines.sql
*   sqlplus user/password@yourdb @sql_baselines.sql SQL_0123456789abcdef
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

COLUMN sql_handle     FORMAT A20              HEADING 'SQL Handle'
COLUMN plan_name      FORMAT A30              HEADING 'Plan Name'
COLUMN creator        FORMAT A15              HEADING 'Creator'
COLUMN origin         FORMAT A16              HEADING 'Origin'
COLUMN enabled        FORMAT A4               HEADING 'Ena'
COLUMN accepted       FORMAT A4               HEADING 'Acc'
COLUMN fixed          FORMAT A4               HEADING 'Fix'
COLUMN reproduced     FORMAT A4               HEADING 'Rep'
COLUMN autopurge      FORMAT A4               HEADING 'Prg'
COLUMN executions     FORMAT 999,999,999      HEADING 'Execs'
COLUMN ela_per_exec   FORMAT 999,990.4000     HEADING 'Ela/Exec'
COLUMN cpu_per_exec   FORMAT 999,990.4000     HEADING 'CPU/Exec'
COLUMN gets_per_exec  FORMAT 999,999,999      HEADING 'Gets/Exec'
COLUMN created_time   FORMAT A16              HEADING 'Created'
COLUMN last_exec_time FORMAT A16              HEADING 'Last Executed'
COLUMN sql_text       FORMAT A50 TRUNC        HEADING 'SQL Text'

PROMPT
PROMPT === SQL Plan Baselines (DBA_SQL_PLAN_BASELINES) ===
PROMPT

SELECT
    sql_handle,
    plan_name,
    creator,
    origin,
    enabled,
    accepted,
    fixed,
    reproduced,
    autopurge,
    executions,
    ROUND(elapsed_time / NULLIF(executions, 0) / 1e6, 4) AS ela_per_exec,
    ROUND(cpu_time / NULLIF(executions, 0) / 1e6, 4) AS cpu_per_exec,
    ROUND(buffer_gets / NULLIF(executions, 0), 0) AS gets_per_exec,
    TO_CHAR(created, 'YYYY-MM-DD HH24:MI') AS created_time,
    TO_CHAR(last_executed, 'YYYY-MM-DD HH24:MI') AS last_exec_time,
    SUBSTR(sql_text, 1, 50) AS sql_text
FROM dba_sql_plan_baselines
WHERE (sql_handle LIKE UPPER('&&p_filter')
   OR plan_name LIKE UPPER('&&p_filter')
   OR UPPER(sql_text) LIKE '%' || UPPER('&&p_filter') || '%')
ORDER BY created DESC, sql_handle, plan_name;

COLUMN sql_handle CLEAR
COLUMN plan_name CLEAR
COLUMN creator CLEAR
COLUMN origin CLEAR
COLUMN enabled CLEAR
COLUMN accepted CLEAR
COLUMN fixed CLEAR
COLUMN reproduced CLEAR
COLUMN autopurge CLEAR
COLUMN executions CLEAR
COLUMN ela_per_exec CLEAR
COLUMN cpu_per_exec CLEAR
COLUMN gets_per_exec CLEAR
COLUMN created_time CLEAR
COLUMN last_exec_time CLEAR
COLUMN sql_text CLEAR
COLUMN c_filter CLEAR

UNDEFINE p_filter
UNDEFINE 1

SET FEEDBACK ON
SET VERIFY ON
