/*******************************************************************************
*
* Script Name: table_io_stats.sql
* Title: Table I/O wait statistics
* Tags: I/O, Performance, Tables
* Purpose: Reports tables experiencing the highest I/O wait times and operation counts
*
* Description:
*   Queries Performance Schema table I/O summaries to pinpoint tables generating
*   the highest read and write I/O latency across all user schemas.
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT on performance_schema.table_io_waits_summary_by_table
*
* Output Format:
*   - schema_name: Database / schema name
*   - table_name: Table name
*   - total_io_ops: Total I/O operations
*   - total_wait_sec: Total I/O wait time in seconds
*   - read_ops: Total read operations (fetches)
*   - read_wait_sec: Read wait latency in seconds
*   - write_ops: Total write operations (inserts, updates, deletes)
*   - write_wait_sec: Write wait latency in seconds
*
* Example Usage:
*   mysql -u root -p < table_io_stats.sql
*   mysql> source table_io_stats.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    object_schema AS schema_name,
    object_name AS table_name,
    count_star AS total_io_ops,
    ROUND(sum_timer_wait / 1000000000000, 3) AS total_wait_sec,
    count_read AS read_ops,
    ROUND(sum_timer_read / 1000000000000, 3) AS read_wait_sec,
    count_write AS write_ops,
    ROUND(sum_timer_write / 1000000000000, 3) AS write_wait_sec
FROM performance_schema.table_io_waits_summary_by_table
WHERE object_schema NOT IN ('information_schema', 'performance_schema', 'sys', 'mysql')
  AND count_star > 0
ORDER BY sum_timer_wait DESC
LIMIT 30;
