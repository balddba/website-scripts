/*******************************************************************************
*
* Script Name: blocking_sessions.sql
* Title: Blocking sessions
* Tags: Locks, Sessions, Performance
* Purpose: Reports sessions waiting behind another session
*
* Description:
*   Uses Performance Schema lock wait data to connect waiting sessions to the
*   blocking sessions holding the conflicting lock. Includes processlist IDs,
*   account details, schemas, and current statements when available.
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT on performance_schema.data_lock_waits
*   - SELECT on performance_schema.data_locks
*   - SELECT on performance_schema.threads
*   - SELECT on performance_schema.events_statements_current
*
* Output Format:
*   - waiting_thread_id: Performance Schema thread ID for the waiting session
*   - waiting_processlist_id: MySQL connection ID for the waiting session
*   - waiting_user: Waiting account user
*   - waiting_host: Waiting account host
*   - waiting_schema: Default schema for waiting session
*   - waiting_query: Current waiting SQL text
*   - blocking_thread_id: Performance Schema thread ID for the blocker
*   - blocking_processlist_id: MySQL connection ID for the blocker
*   - blocking_user: Blocking account user
*   - blocking_host: Blocking account host
*   - blocking_query: Current blocking SQL text, or idle marker
*
* Example Usage:
*   mysql -u root -p < blocking_sessions.sql
*   mysql> source blocking_sessions.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    waiting_lock.thread_id AS waiting_thread_id,
    waiting_thread.processlist_id AS waiting_processlist_id,
    waiting_thread.processlist_user AS waiting_user,
    waiting_thread.processlist_host AS waiting_host,
    waiting_thread.processlist_db AS waiting_schema,
    waiting_stmt.sql_text AS waiting_query,
    blocking_lock.thread_id AS blocking_thread_id,
    blocking_thread.processlist_id AS blocking_processlist_id,
    blocking_thread.processlist_user AS blocking_user,
    blocking_thread.processlist_host AS blocking_host,
    COALESCE(blocking_stmt.sql_text, '<idle or statement not instrumented>') AS blocking_query
FROM performance_schema.data_lock_waits AS waits
JOIN performance_schema.data_locks AS waiting_lock
    ON waiting_lock.engine_lock_id = waits.requesting_engine_lock_id
JOIN performance_schema.data_locks AS blocking_lock
    ON blocking_lock.engine_lock_id = waits.blocking_engine_lock_id
LEFT JOIN performance_schema.threads AS waiting_thread
    ON waiting_thread.thread_id = waiting_lock.thread_id
LEFT JOIN performance_schema.threads AS blocking_thread
    ON blocking_thread.thread_id = blocking_lock.thread_id
LEFT JOIN performance_schema.events_statements_current AS waiting_stmt
    ON waiting_stmt.thread_id = waiting_lock.thread_id
LEFT JOIN performance_schema.events_statements_current AS blocking_stmt
    ON blocking_stmt.thread_id = blocking_lock.thread_id
ORDER BY waiting_thread.processlist_time DESC, waiting_thread.processlist_id;
