/*******************************************************************************
*
* Script Name: session_memory_usage.sql
* Title: Session memory usage
* Tags: Memory, Sessions, Performance
* Purpose: Reports current memory usage by active session
*
* Description:
*   Summarizes Performance Schema memory instrumentation by thread and joins it
*   to session details so active connections can be ranked by memory allocation.
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT on performance_schema.memory_summary_by_thread_by_event_name
*   - SELECT on performance_schema.threads
*   - SELECT on performance_schema.events_statements_current
*
* Output Format:
*   - thread_id: Performance Schema thread ID
*   - processlist_id: MySQL connection ID
*   - user: Session user
*   - host: Session host
*   - db: Default database
*   - current_alloc_mb: Current allocated memory in MB
*   - total_allocated_mb: Total allocated memory in MB since thread start
*   - current_statement: Current SQL text when available
*
* Example Usage:
*   mysql -u root -p < session_memory_usage.sql
*   mysql> source session_memory_usage.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    t.thread_id,
    t.processlist_id,
    t.processlist_user AS user,
    t.processlist_host AS host,
    t.processlist_db AS db,
    ROUND(SUM(COALESCE(m.current_number_of_bytes_used, 0)) / 1024 / 1024, 2) AS current_alloc_mb,
    ROUND(SUM(COALESCE(m.sum_number_of_bytes_alloc, 0)) / 1024 / 1024, 2) AS total_allocated_mb,
    COALESCE(s.sql_text, '<idle or statement not instrumented>') AS current_statement
FROM performance_schema.threads AS t
LEFT JOIN performance_schema.memory_summary_by_thread_by_event_name AS m
    ON m.thread_id = t.thread_id
LEFT JOIN performance_schema.events_statements_current AS s
    ON s.thread_id = t.thread_id
WHERE t.type = 'FOREGROUND'
GROUP BY
    t.thread_id,
    t.processlist_id,
    t.processlist_user,
    t.processlist_host,
    t.processlist_db,
    s.sql_text
ORDER BY current_alloc_mb DESC, total_allocated_mb DESC;
