/*******************************************************************************
*
* Script Name: innodb_engine_metrics.sql
* Title: InnoDB engine metrics snapshot
* Tags: InnoDB, I/O, Locks, Performance
* Purpose: Reports row operations, lock waits, redo logging, and page I/O counters
*
* Description:
*   Collects operational activity counters from the InnoDB storage engine,
*   highlighting row lock wait times, redo log write pressure, data page I/O,
*   and row modification rates.
*
* Parameters:
*   None
*
* Required Privileges:
*   - PROCESS (or SELECT on performance_schema.global_status)
*
* Output Format:
*   - category: Metric grouping category
*   - metric: Specific InnoDB counter name
*   - value: Current counter value
*
* Example Usage:
*   mysql -u root -p < innodb_engine_metrics.sql
*   mysql> source innodb_engine_metrics.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    'Locking' AS category,
    'Row Lock Waits' AS metric,
    CAST(VARIABLE_VALUE AS CHAR) AS value
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_row_lock_waits'
UNION ALL
SELECT
    'Locking',
    'Total Lock Wait Time (ms)',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_row_lock_time'
UNION ALL
SELECT
    'Locking',
    'Avg Lock Wait Time (ms)',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_row_lock_time_avg'
UNION ALL
SELECT
    'Row Activity',
    'Rows Read',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_rows_read'
UNION ALL
SELECT
    'Row Activity',
    'Rows Inserted',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_rows_inserted'
UNION ALL
SELECT
    'Row Activity',
    'Rows Updated',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_rows_updated'
UNION ALL
SELECT
    'Row Activity',
    'Rows Deleted',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_rows_deleted'
UNION ALL
SELECT
    'Redo Log / I/O',
    'OS Log Bytes Written',
    CONCAT(ROUND(CAST(VARIABLE_VALUE AS DECIMAL(20, 2)) / 1024 / 1024, 2), ' MB')
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_os_log_written'
UNION ALL
SELECT
    'Redo Log / I/O',
    'OS Log Fsyncs',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_os_log_fsyncs'
UNION ALL
SELECT
    'Redo Log / I/O',
    'Log Buffer Waits (Flush Contention)',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_log_waits'
UNION ALL
SELECT
    'Page I/O',
    'Data Pages Read',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_pages_read'
UNION ALL
SELECT
    'Page I/O',
    'Data Pages Written',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_pages_written'
UNION ALL
SELECT
    'Page I/O',
    'Data Pages Created',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_pages_created';
