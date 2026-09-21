/*******************************************************************************
*
* Script Name: ash_wait_chains.sql
* Title: ASH Wait Chains
* Tags: Performance, ASH, Locks
* Purpose: Analyzes active session wait chains and blockers over recent ASH samples
*
* Description:
*   Queries GV$ACTIVE_SESSION_HISTORY to trace active session wait chains and
*   blocker relationships across instances over a specified time window.
*   Displays waiting sessions along with their blocking session, blocking instance,
*   wait event, SQL ID, and the number of sample occurrences.
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
*   - Waiting Session ID and Serial#
*   - Waiting SQL ID
*   - Wait Event and Wait Class
*   - Blocking Instance ID and Blocking Session ID
*   - Blocking SQL ID
*   - Sample Count
*   - Percentage of Chain Activity
*
* Example Usage:
*   sqlplus user/password@yourdb @ash_wait_chains.sql
*   sqlplus user/password@yourdb @ash_wait_chains.sql 30
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

COLUMN inst_id          FORMAT 999             HEADING 'Inst'
COLUMN session_id       FORMAT 99999           HEADING 'SID'
COLUMN session_serial#  FORMAT 99999999        HEADING 'Serial#'
COLUMN sql_id           FORMAT A13             HEADING 'SQL ID'
COLUMN event            FORMAT A30 TRUNC       HEADING 'Event'
COLUMN wait_class       FORMAT A15 TRUNC       HEADING 'Wait Class'
COLUMN blocking_inst_id FORMAT 999             HEADING 'Blk Inst'
COLUMN blocking_session FORMAT 99999           HEADING 'Blk SID'
COLUMN blocking_sql_id  FORMAT A13             HEADING 'Blk SQL ID'
COLUMN sample_count     FORMAT 999,999         HEADING 'Samples'
COLUMN pct_chain        FORMAT 990.0           HEADING 'Pct'

PROMPT
PROMPT === ASH Active Wait Chains and Blockers (Last &&p_mins minutes) ===
PROMPT

SELECT *
FROM (
    SELECT
        h.inst_id,
        h.session_id,
        h.session_serial#,
        h.sql_id,
        NVL(h.event, h.session_state) AS event,
        NVL(h.wait_class, 'CPU') AS wait_class,
        h.blocking_inst_id,
        h.blocking_session,
        b.sql_id AS blocking_sql_id,
        COUNT(*) AS sample_count,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct_chain
    FROM gv$active_session_history h
    LEFT JOIN gv$active_session_history b
      ON b.inst_id = h.blocking_inst_id
     AND b.session_id = h.blocking_session
     AND b.sample_id = h.sample_id
    WHERE h.sample_time >= SYSTIMESTAMP - NUMTODSINTERVAL(TO_NUMBER('&&p_mins'), 'MINUTE')
      AND (h.blocking_session IS NOT NULL OR h.session_id IN (
          SELECT blocking_session
          FROM gv$active_session_history
          WHERE blocking_session IS NOT NULL
            AND sample_time >= SYSTIMESTAMP - NUMTODSINTERVAL(TO_NUMBER('&&p_mins'), 'MINUTE')
      ))
    GROUP BY
        h.inst_id,
        h.session_id,
        h.session_serial#,
        h.sql_id,
        NVL(h.event, h.session_state),
        NVL(h.wait_class, 'CPU'),
        h.blocking_inst_id,
        h.blocking_session,
        b.sql_id
    ORDER BY sample_count DESC
)
WHERE ROWNUM <= 50;

COLUMN c_mins CLEAR
COLUMN inst_id CLEAR
COLUMN session_id CLEAR
COLUMN session_serial# CLEAR
COLUMN sql_id CLEAR
COLUMN event CLEAR
COLUMN wait_class CLEAR
COLUMN blocking_inst_id CLEAR
COLUMN blocking_session CLEAR
COLUMN blocking_sql_id CLEAR
COLUMN sample_count CLEAR
COLUMN pct_chain CLEAR

SET FEEDBACK ON
SET VERIFY ON
