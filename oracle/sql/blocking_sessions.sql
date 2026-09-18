/*******************************************************************************
*
* Script Name: blocking_sessions.sql
* Title: Blocking sessions
* Tags: Performance, Locks
* Purpose: Identify blocking and waiting sessions, with wait event and SQL ID details
*
* Description:
*   Lists blockers and waiters from GV$SESSION across RAC and single-instance
*   databases. Useful for diagnosing lock contention.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on GV$SESSION
*
* Output Format:
*   - Instance, SID, serial, username, status, wait event, wait seconds, SQL ID
*   - Blocking instance and blocking session
*
* Example Usage:
*   sqlplus user/password@yourdb @blocking_sessions.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    s.inst_id,
    s.sid,
    s.serial#,
    s.username,
    s.status,
    s.event,
    s.seconds_in_wait,
    s.sql_id,
    s.blocking_instance,
    s.blocking_session
FROM gv$session s
WHERE s.blocking_session IS NOT NULL
   OR s.sid IN (
        SELECT blocking_session
        FROM gv$session
        WHERE blocking_session IS NOT NULL
    )
ORDER BY s.blocking_session NULLS FIRST, s.seconds_in_wait DESC;
