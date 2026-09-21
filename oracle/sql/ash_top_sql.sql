/*******************************************************************************
*
* Script Name: ash_top_sql.sql
* Title: ASH Top SQL
* Tags: Performance, ASH
* Purpose: Ranks top SQL IDs and wait events over a time window (default last 15 minutes, optional &1 in minutes) from gv$active_session_history
*
* Description:
*   Queries GV$ACTIVE_SESSION_HISTORY to identify the top SQL statements and
*   their associated wait events or CPU activity over a specified time window.
*   Helps pinpoint transient performance spikes and top resource-consuming SQL.
*
* Parameters:
*   &1 - (Optional) Time window in minutes to look back. Default 15.
*
* Required Privileges:
*   - SELECT on GV$ACTIVE_SESSION_HISTORY
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Instance ID
*   - SQL ID
*   - SQL Operation Name
*   - Session State (WAITING / ON CPU)
*   - Wait Class
*   - Wait Event
*   - Sample Count
*   - Percentage of Activity
*
* Example Usage:
*   sqlplus user/password@yourdb @ash_top_sql.sql
*   sqlplus user/password@yourdb @ash_top_sql.sql 30
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

COLUMN c_mins NEW_VALUE p_mins NOPRINT
SELECT NVL(NULLIF(TRIM('&1'), ''), '15') AS c_mins FROM dual;

COLUMN inst_id       FORMAT 999             HEADING 'Inst'
COLUMN sql_id        FORMAT A13             HEADING 'SQL ID'
COLUMN sql_opname    FORMAT A15 TRUNC       HEADING 'SQL Op'
COLUMN session_state FORMAT A10             HEADING 'State'
COLUMN wait_class    FORMAT A18 TRUNC       HEADING 'Wait Class'
COLUMN event         FORMAT A32 TRUNC       HEADING 'Event'
COLUMN sample_count  FORMAT 999,999         HEADING 'Samples'
COLUMN pct_activity  FORMAT 990.0           HEADING 'Pct Activity'

PROMPT
PROMPT === Top SQL and Wait Events from ASH (Last &&p_mins minutes) ===
PROMPT

SELECT *
FROM (
    SELECT
        inst_id,
        sql_id,
        sql_opname,
        session_state,
        NVL(wait_class, 'CPU') AS wait_class,
        NVL(event, 'ON CPU') AS event,
        COUNT(*) AS sample_count,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct_activity
    FROM gv$active_session_history
    WHERE sample_time >= SYSTIMESTAMP - NUMTODSINTERVAL(TO_NUMBER('&&p_mins'), 'MINUTE')
      AND sql_id IS NOT NULL
    GROUP BY
        inst_id,
        sql_id,
        sql_opname,
        session_state,
        NVL(wait_class, 'CPU'),
        NVL(event, 'ON CPU')
    ORDER BY sample_count DESC
)
WHERE ROWNUM <= 50;

COLUMN c_mins CLEAR
COLUMN inst_id CLEAR
COLUMN sql_id CLEAR
COLUMN sql_opname CLEAR
COLUMN session_state CLEAR
COLUMN wait_class CLEAR
COLUMN event CLEAR
COLUMN sample_count CLEAR
COLUMN pct_activity CLEAR

SET FEEDBACK ON
SET VERIFY ON
