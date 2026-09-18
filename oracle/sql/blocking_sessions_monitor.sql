/*******************************************************************************
*
* Script Name: blocking_sessions_monitor.sql
* Title: Blocking sessions monitor
* Tags: Performance, Locks
* Purpose: Monitor blocking sessions with blocker, waiter, wait event, and SQL details
*
* Description:
*   Reports current blocking relationships, a summary of blocking sessions,
*   and details of blocked sessions including wait events. Results are sorted
*   by wait time in descending order. Machine names are truncated to 30
*   characters and SQL text to 50 characters.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$SESSION
*   - SELECT on V$LOCK
*   - SELECT on V$SQLAREA
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Current blocking relationships with wait times
*   - Summary of blocking sessions and how many sessions they block
*   - Details of blocked sessions including wait events
*
* Example Usage:
*   SQL> @blocking_sessions_monitor.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/
SET LINESIZE 200
SET PAGESIZE 1000
    COLUMN blocking_status FORMAT A100
    COLUMN wait_event FORMAT A30
    COLUMN sql_text FORMAT A50
    CLEAR BREAKS
    CLEAR COMPUTES
    PROMPT =====================================================================
    PROMPT BLOCKING SESSIONS MONITOR
    PROMPT =====================================================================

-- Main blocking sessions report
SELECT s1.username || '@' || s1.machine ||
       ' (SID=' || s1.sid || ',SERIAL#=' || s1.serial# || ') is blocking ' ||
       s2.username || '@' || s2.machine ||
       ' (SID=' || s2.sid || ',SERIAL#=' || s2.serial# || ')' as blocking_status,
       s2.event                                               as wait_event,
       s2.seconds_in_wait                                     as waiting_seconds,
       SUBSTR(sa.sql_text, 1, 50)                             as sql_text
FROM v$lock l1
         JOIN v$session s1 ON s1.sid = l1.sid
         JOIN v$lock l2 ON l1.id1 = l2.id1 AND l1.id2 = l2.id2
         JOIN v$session s2 ON s2.sid = l2.sid
         LEFT JOIN v$sqlarea sa ON s1.sql_id = sa.sql_id
WHERE l1.BLOCK = 1
  AND l2.request > 0
ORDER BY s2.seconds_in_wait DESC;

PROMPT
PROMPT Blocking Sessions Detail Report:
PROMPT =====================================================================

-- Blocking sessions summary
SELECT s1.sid                     as blocker_sid,
       s1.serial#                 as serial#,
       s1.username,
       s1.program,
       SUBSTR(s1.machine, 1, 30)  as machine,
       COUNT(*)                   as blocking_count,
       SUBSTR(sa.sql_text, 1, 50) as sql_text
FROM v$lock l1
         JOIN v$session s1 ON s1.sid = l1.sid
         JOIN v$lock l2 ON l1.id1 = l2.id1 AND l1.id2 = l2.id2
         JOIN v$session s2 ON s2.sid = l2.sid
         LEFT JOIN v$sqlarea sa ON s1.sql_id = sa.sql_id
WHERE l1.BLOCK = 1
  AND l2.request > 0
GROUP BY s1.sid,
         s1.serial#,
         s1.username,
         s1.program,
         s1.machine,
         sa.sql_text
ORDER BY COUNT(*) DESC;

PROMPT
PROMPT Blocked Sessions Detail Report:
PROMPT =====================================================================

-- Blocked sessions details
SELECT s2.sid,
       s2.serial#,
       s2.username,
       s2.program,
       SUBSTR(s2.machine, 1, 30) as machine,
       s2.event                  as wait_event,
       s2.seconds_in_wait        as waiting_seconds
FROM v$lock l1
         JOIN v$session s1 ON s1.sid = l1.sid
         JOIN v$lock l2 ON l1.id1 = l2.id1 AND l1.id2 = l2.id2
         JOIN v$session s2 ON s2.sid = l2.sid
WHERE l1.BLOCK = 1
  AND l2.request > 0
ORDER BY s2.seconds_in_wait DESC;

PROMPT
PROMPT =====================================================================