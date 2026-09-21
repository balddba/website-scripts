/*******************************************************************************
*
* Script Name: scheduler_jobs.sql
* Title: DBMS_SCHEDULER jobs
* Tags: Scheduler, Jobs, Diagnostics
* Purpose: Report DBMS_SCHEDULER jobs, current runs, upcoming work, and recent failures
*
* Description:
*   Lists Scheduler jobs from DBA_SCHEDULER_JOBS with enabled flag, state,
*   schedule, last and next run, and failure counts. Running jobs, the next
*   24 hours of scheduled work, run-history totals, and failed or stopped
*   runs from the last 7 days are included. SYSTEM=TRUE jobs are Oracle-
*   supplied. Run it in the container you care about (CDB root or a PDB).
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on DBA_SCHEDULER_JOBS
*   - SELECT on DBA_SCHEDULER_RUNNING_JOBS
*   - SELECT on DBA_SCHEDULER_JOB_RUN_DETAILS
*   - SELECT on DBA_SCHEDULER_GLOBAL_ATTRIBUTE
*   - SELECT on DBA_SCHEDULER_WINDOWS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Scheduler attributes and currently open windows
*   - Job counts by owner and state
*   - Job inventory (type, schedule, last/next run, run and failure counts)
*   - Currently running jobs
*   - Jobs due in the next 24 hours
*   - Run-history counts for the last 7 days
*   - Failed or stopped runs in the last 7 days
*
* Example Usage:
*   SQL> @scheduler_jobs.sql
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
SET NULL '(null)'

COLUMN attribute            FORMAT A32               HEADING 'Attribute'
COLUMN attr_value           FORMAT A80               HEADING 'Value'
COLUMN window_name          FORMAT A30               HEADING 'Window'
COLUMN resource_plan        FORMAT A30               HEADING 'Resource Plan'
COLUMN window_duration      FORMAT A20               HEADING 'Duration'
COLUMN next_start           FORMAT A25               HEADING 'Next Start'
COLUMN owner                FORMAT A30               HEADING 'Owner'
COLUMN job_count            FORMAT 999,990           HEADING 'Jobs'
COLUMN enabled_count        FORMAT 999,990           HEADING 'Enabled'
COLUMN disabled_count       FORMAT 999,990           HEADING 'Disabled'
COLUMN running_count        FORMAT 999,990           HEADING 'Running'
COLUMN broken_count         FORMAT 999,990           HEADING 'Broken'
COLUMN failed_count         FORMAT 999,990           HEADING 'Failed'
COLUMN job_name             FORMAT A30               HEADING 'Job Name'
COLUMN job_subname          FORMAT A20               HEADING 'Subname'
COLUMN system_job           FORMAT A6                HEADING 'System'
COLUMN job_type             FORMAT A18               HEADING 'Job Type'
COLUMN job_action           FORMAT A50 TRUNC         HEADING 'Action'
COLUMN job_class            FORMAT A24               HEADING 'Job Class'
COLUMN enabled              FORMAT A8                HEADING 'Enabled'
COLUMN state                FORMAT A20               HEADING 'State'
COLUMN schedule_type        FORMAT A16               HEADING 'Sched Type'
COLUMN repeat_interval      FORMAT A40 TRUNC         HEADING 'Repeat Interval'
COLUMN last_start           FORMAT A19               HEADING 'Last Start'
COLUMN last_duration        FORMAT A16               HEADING 'Last Duration'
COLUMN next_run             FORMAT A25               HEADING 'Next Run'
COLUMN run_count            FORMAT 999,999,990       HEADING 'Runs'
COLUMN failure_count        FORMAT 999,990           HEADING 'Failures'
COLUMN max_failures         FORMAT 999,990           HEADING 'Max Fail'
COLUMN retry_count          FORMAT 999,990           HEADING 'Retries'
COLUMN comments             FORMAT A40 TRUNC         HEADING 'Comments'
COLUMN session_id           FORMAT 999999990         HEADING 'SID'
COLUMN slave_os_pid         FORMAT A12               HEADING 'OS PID'
COLUMN running_instance     FORMAT 9990              HEADING 'Inst'
COLUMN elapsed_time         FORMAT A16               HEADING 'Elapsed'
COLUMN cpu_used             FORMAT A16               HEADING 'CPU'
COLUMN consumer_group       FORMAT A24               HEADING 'Consumer Group'
COLUMN status               FORMAT A12               HEADING 'Status'
COLUMN runs                 FORMAT 999,999,990       HEADING 'Runs'
COLUMN first_run            FORMAT A19               HEADING 'First Run'
COLUMN last_run             FORMAT A19               HEADING 'Last Run'
COLUMN log_date             FORMAT A19               HEADING 'Log Date'
COLUMN actual_start         FORMAT A19               HEADING 'Actual Start'
COLUMN run_duration         FORMAT A16               HEADING 'Duration'
COLUMN error#               FORMAT 999999990         HEADING 'Error#'
COLUMN additional_info      FORMAT A70 TRUNC         HEADING 'Additional Info'

PROMPT
PROMPT === Scheduler attributes ===
PROMPT

SELECT
    attribute_name AS attribute,
    value AS attr_value
FROM dba_scheduler_global_attribute
ORDER BY attribute_name;

PROMPT
PROMPT === Open windows ===
PROMPT

SELECT
    window_name,
    resource_plan,
    enabled,
    active AS state,
    TO_CHAR(duration) AS window_duration,
    TO_CHAR(next_start_date, 'YYYY-MM-DD HH24:MI:SS TZR') AS next_start
FROM dba_scheduler_windows
WHERE active = 'TRUE'
ORDER BY window_name;

PROMPT
PROMPT === Job counts by owner ===
PROMPT

SELECT
    owner,
    COUNT(*) AS job_count,
    SUM(CASE WHEN enabled = 'TRUE' THEN 1 ELSE 0 END) AS enabled_count,
    SUM(CASE WHEN enabled = 'FALSE' THEN 1 ELSE 0 END) AS disabled_count,
    SUM(CASE WHEN state = 'RUNNING' THEN 1 ELSE 0 END) AS running_count,
    SUM(CASE WHEN state = 'BROKEN' THEN 1 ELSE 0 END) AS broken_count,
    SUM(failure_count) AS failed_count
FROM dba_scheduler_jobs
GROUP BY owner
ORDER BY
    SUM(CASE WHEN NVL(system, 'FALSE') = 'FALSE' THEN 0 ELSE 1 END),
    owner;

PROMPT
PROMPT === Job inventory ===
PROMPT
PROMPT SYSTEM=TRUE jobs are Oracle-supplied. User jobs are listed first.
PROMPT

SELECT
    owner,
    job_name,
    NVL(system, 'FALSE') AS system_job,
    job_type,
    SUBSTR(REPLACE(REPLACE(job_action, CHR(10), ' '), CHR(13), ' '), 1, 50) AS job_action,
    job_class,
    enabled,
    state,
    schedule_type,
    repeat_interval,
    TO_CHAR(last_start_date, 'YYYY-MM-DD HH24:MI:SS') AS last_start,
    TO_CHAR(last_run_duration) AS last_duration,
    TO_CHAR(next_run_date, 'YYYY-MM-DD HH24:MI:SS TZR') AS next_run,
    run_count,
    failure_count,
    max_failures,
    comments
FROM dba_scheduler_jobs
ORDER BY
    CASE WHEN NVL(system, 'FALSE') = 'FALSE' THEN 0 ELSE 1 END,
    CASE state
        WHEN 'BROKEN' THEN 0
        WHEN 'FAILED' THEN 1
        WHEN 'RUNNING' THEN 2
        WHEN 'CHAIN_STALLED' THEN 3
        ELSE 4
    END,
    owner,
    job_name;

PROMPT
PROMPT === Currently running ===
PROMPT

SELECT
    r.owner,
    r.job_name,
    r.job_subname,
    r.session_id,
    r.slave_os_process_id AS slave_os_pid,
    r.running_instance,
    TO_CHAR(r.elapsed_time) AS elapsed_time,
    TO_CHAR(r.cpu_used) AS cpu_used,
    r.resource_consumer_group AS consumer_group
FROM dba_scheduler_running_jobs r
ORDER BY r.running_instance, r.owner, r.job_name;

PROMPT
PROMPT === Due in the next 24 hours ===
PROMPT

SELECT
    owner,
    job_name,
    NVL(system, 'FALSE') AS system_job,
    enabled,
    state,
    TO_CHAR(next_run_date, 'YYYY-MM-DD HH24:MI:SS TZR') AS next_run,
    repeat_interval
FROM dba_scheduler_jobs
WHERE enabled = 'TRUE'
  AND next_run_date IS NOT NULL
  AND next_run_date <= SYSTIMESTAMP + INTERVAL '1' DAY
ORDER BY next_run_date, owner, job_name;

PROMPT
PROMPT === Run history last 7 days ===
PROMPT

SELECT
    owner,
    job_name,
    status,
    COUNT(*) AS runs,
    TO_CHAR(MIN(actual_start_date), 'YYYY-MM-DD HH24:MI:SS') AS first_run,
    TO_CHAR(MAX(actual_start_date), 'YYYY-MM-DD HH24:MI:SS') AS last_run
FROM dba_scheduler_job_run_details
WHERE log_date >= SYSTIMESTAMP - INTERVAL '7' DAY
GROUP BY owner, job_name, status
ORDER BY
    CASE status
        WHEN 'FAILED' THEN 0
        WHEN 'STOPPED' THEN 1
        ELSE 2
    END,
    owner,
    job_name,
    status;

PROMPT
PROMPT === Failed or stopped runs last 7 days ===
PROMPT

SELECT
    TO_CHAR(log_date, 'YYYY-MM-DD HH24:MI:SS') AS log_date,
    owner,
    job_name,
    status,
    error#,
    TO_CHAR(actual_start_date, 'YYYY-MM-DD HH24:MI:SS') AS actual_start,
    TO_CHAR(run_duration) AS run_duration,
    SUBSTR(REPLACE(REPLACE(additional_info, CHR(10), ' '), CHR(13), ' '), 1, 70) AS additional_info
FROM dba_scheduler_job_run_details
WHERE log_date >= SYSTIMESTAMP - INTERVAL '7' DAY
  AND status != 'SUCCEEDED'
ORDER BY log_date DESC, owner, job_name;

COLUMN attribute CLEAR
COLUMN attr_value CLEAR
COLUMN window_name CLEAR
COLUMN resource_plan CLEAR
COLUMN window_duration CLEAR
COLUMN next_start CLEAR
COLUMN owner CLEAR
COLUMN job_count CLEAR
COLUMN enabled_count CLEAR
COLUMN disabled_count CLEAR
COLUMN running_count CLEAR
COLUMN broken_count CLEAR
COLUMN failed_count CLEAR
COLUMN job_name CLEAR
COLUMN job_subname CLEAR
COLUMN system_job CLEAR
COLUMN job_type CLEAR
COLUMN job_action CLEAR
COLUMN job_class CLEAR
COLUMN enabled CLEAR
COLUMN state CLEAR
COLUMN schedule_type CLEAR
COLUMN repeat_interval CLEAR
COLUMN last_start CLEAR
COLUMN last_duration CLEAR
COLUMN next_run CLEAR
COLUMN run_count CLEAR
COLUMN failure_count CLEAR
COLUMN max_failures CLEAR
COLUMN retry_count CLEAR
COLUMN comments CLEAR
COLUMN session_id CLEAR
COLUMN slave_os_pid CLEAR
COLUMN running_instance CLEAR
COLUMN elapsed_time CLEAR
COLUMN cpu_used CLEAR
COLUMN consumer_group CLEAR
COLUMN status CLEAR
COLUMN runs CLEAR
COLUMN first_run CLEAR
COLUMN last_run CLEAR
COLUMN log_date CLEAR
COLUMN actual_start CLEAR
COLUMN run_duration CLEAR
COLUMN error# CLEAR
COLUMN additional_info CLEAR

SET FEEDBACK ON
SET VERIFY ON
SET NULL ''
