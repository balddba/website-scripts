/*******************************************************************************
*
* Script Name: system_wait_events.sql
* Title: System Wait Events
* Tags: Performance, Waits
* Purpose: Reports instance-level wait profile from gv$system_event, filtering out Idle wait classes and sorting by total time waited
*
* Description:
*   Queries GV$SYSTEM_EVENT to produce an instance-level wait event profile.
*   Excludes the Idle wait class and sorts wait events by total time waited.
*   Provides total waits, timeouts, elapsed time in seconds, and average wait time in milliseconds.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on GV$SYSTEM_EVENT
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Instance ID
*   - Wait Event Name
*   - Wait Class
*   - Total Waits
*   - Total Timeouts
*   - Total Time Waited (seconds)
*   - Average Wait (milliseconds)
*   - Percentage of Total Wait Time
*
* Example Usage:
*   sqlplus user/password@yourdb @system_wait_events.sql
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

COLUMN inst_id        FORMAT 999             HEADING 'Inst'
COLUMN event          FORMAT A40 TRUNC       HEADING 'Event'
COLUMN wait_class     FORMAT A18 TRUNC       HEADING 'Wait Class'
COLUMN total_waits    FORMAT 999,999,999     HEADING 'Total Waits'
COLUMN total_timeouts FORMAT 999,999,999     HEADING 'Timeouts'
COLUMN time_waited_s  FORMAT 999,999,990.00  HEADING 'Time Waited (s)'
COLUMN avg_wait_ms    FORMAT 999,990.00      HEADING 'Avg Wait (ms)'
COLUMN pct_time       FORMAT 990.00          HEADING 'Pct Time'

PROMPT
PROMPT === System Non-Idle Wait Events ===
PROMPT

SELECT *
FROM (
    SELECT
        inst_id,
        event,
        wait_class,
        total_waits,
        total_timeouts,
        ROUND(time_waited_micro / 1000000.0, 2) AS time_waited_s,
        ROUND(time_waited_micro / 1000.0 / NULLIF(total_waits, 0), 2) AS avg_wait_ms,
        ROUND(time_waited_micro * 100.0 / NULLIF(SUM(time_waited_micro) OVER (PARTITION BY inst_id), 0), 2) AS pct_time
    FROM gv$system_event
    WHERE wait_class <> 'Idle'
      AND total_waits > 0
    ORDER BY inst_id, time_waited_micro DESC
)
WHERE ROWNUM <= 50;

COLUMN inst_id CLEAR
COLUMN event CLEAR
COLUMN wait_class CLEAR
COLUMN total_waits CLEAR
COLUMN total_timeouts CLEAR
COLUMN time_waited_s CLEAR
COLUMN avg_wait_ms CLEAR
COLUMN pct_time CLEAR

SET FEEDBACK ON
SET VERIFY ON
