/*******************************************************************************
*
* Script Name: connection_stats.sql
* Title: Connection and thread statistics
* Tags: Connections, Performance, System
* Purpose: Reports connection usage, limits, thread cache metrics, and connection errors
*
* Description:
*   Analyzes current connection utilization against max_connections, evaluates
*   peak connection watermark, thread cache efficiency, and aborted connection counters.
*
* Parameters:
*   None
*
* Required Privileges:
*   - PROCESS (or SELECT on performance_schema.global_status / global_variables)
*
* Output Format:
*   - metric: Metric or setting name
*   - value: Value or formatted percentage
*
* Example Usage:
*   mysql -u root -p < connection_stats.sql
*   mysql> source connection_stats.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    'Max Connections Limit' AS metric,
    CAST(@@max_connections AS CHAR) AS value
UNION ALL
SELECT
    'Current Connected Threads',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Threads_connected'
UNION ALL
SELECT
    'Current Connection Usage Pct',
    CONCAT(ROUND(CAST(VARIABLE_VALUE AS DECIMAL(10, 2)) / @@max_connections * 100, 2), '%')
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Threads_connected'
UNION ALL
SELECT
    'Peak Connections (Max Used)',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Max_used_connections'
UNION ALL
SELECT
    'Peak Connection Usage Pct',
    CONCAT(ROUND(CAST(VARIABLE_VALUE AS DECIMAL(10, 2)) / @@max_connections * 100, 2), '%')
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Max_used_connections'
UNION ALL
SELECT
    'Active Running Threads',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Threads_running'
UNION ALL
SELECT
    'Cached Threads',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Threads_cached'
UNION ALL
SELECT
    'Thread Cache Size',
    CAST(@@thread_cache_size AS CHAR)
UNION ALL
SELECT
    'Total Connections Handled',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Connections'
UNION ALL
SELECT
    'Threads Created',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Threads_created'
UNION ALL
SELECT
    'Aborted Connections (Handshake / Auth)',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Aborted_connects'
UNION ALL
SELECT
    'Aborted Clients (Dropped / Timeout)',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Aborted_clients'
UNION ALL
SELECT
    'Connection Errors (Max Connections Reached)',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Connection_errors_max_connections';
