/*******************************************************************************
*
* Script Name: top_statements.sql
* Title: Top SQL statements by total execution time
* Tags: Performance, SQL, Workload
* Purpose: Reports top statements ranked by total elapsed execution latency
*
* Description:
*   Queries statement summary digests in Performance Schema to identify queries
*   consuming the highest total CPU/execution time, showing execution counts,
*   average and maximum latency, rows examined vs sent, and full table scans.
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT on performance_schema.events_statements_summary_by_digest
*
* Output Format:
*   - schema_name: Schema where query was executed
*   - query_pattern: Normalized SQL statement digest
*   - exec_count: Number of executions
*   - total_sec: Total execution time in seconds
*   - avg_sec: Average execution latency in seconds
*   - max_sec: Maximum observed execution latency in seconds
*   - rows_examined: Total rows examined by storage engines
*   - rows_sent: Total rows returned to clients
*   - no_index_used_count: Executions that performed full table scans
*   - avg_rows_examined: Average rows examined per execution
*
* Example Usage:
*   mysql -u root -p < top_statements.sql
*   mysql> source top_statements.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    COALESCE(schema_name, '') AS schema_name,
    digest_text AS query_pattern,
    count_star AS exec_count,
    ROUND(sum_timer_wait / 1000000000000, 3) AS total_sec,
    ROUND(avg_timer_wait / 1000000000000, 4) AS avg_sec,
    ROUND(max_timer_wait / 1000000000000, 4) AS max_sec,
    sum_rows_examined AS rows_examined,
    sum_rows_sent AS rows_sent,
    sum_no_index_used AS no_index_used_count,
    ROUND(sum_rows_examined / NULLIF(count_star, 0), 1) AS avg_rows_examined
FROM performance_schema.events_statements_summary_by_digest
WHERE digest_text IS NOT NULL
  AND (schema_name IS NULL OR schema_name NOT IN ('information_schema', 'performance_schema', 'sys', 'mysql'))
ORDER BY sum_timer_wait DESC
LIMIT 25;
