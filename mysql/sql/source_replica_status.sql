/*******************************************************************************
*
* Script Name: source_replica_status.sql
* Title: Source and replica status summary
* Tags: Replication, Monitoring, Status
* Purpose: Displays source and replica status metrics from global status counters
*
* Description:
*   Provides a compact replacement-friendly summary for legacy SHOW MASTER
*   STATUS and SHOW SLAVE STATUS checks by reading binary logging and replica
*   status variables exposed through Performance Schema.
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT on performance_schema.global_status
*   - SELECT on performance_schema.global_variables
*
* Output Format:
*   - section: Source, Replica, or Configuration
*   - metric: Status or variable name
*   - value: Current value
*
* Example Usage:
*   mysql -u root -p < source_replica_status.sql
*   mysql> source source_replica_status.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    CASE
        WHEN variable_name IN ('Binlog_cache_disk_use', 'Binlog_cache_use', 'Binlog_stmt_cache_disk_use', 'Binlog_stmt_cache_use') THEN 'Source'
        ELSE 'Replica'
    END AS section,
    variable_name AS metric,
    variable_value AS value
FROM performance_schema.global_status
WHERE variable_name IN (
    'Binlog_cache_disk_use',
    'Binlog_cache_use',
    'Binlog_stmt_cache_disk_use',
    'Binlog_stmt_cache_use',
    'Replica_open_temp_tables',
    'Slave_open_temp_tables',
    'Replica_retried_transactions',
    'Slave_retried_transactions',
    'Replica_running',
    'Slave_running'
)
UNION ALL
SELECT
    'Configuration' AS section,
    variable_name AS metric,
    variable_value AS value
FROM performance_schema.global_variables
WHERE variable_name IN (
    'server_id',
    'server_uuid',
    'log_bin',
    'binlog_format',
    'gtid_mode',
    'read_only',
    'super_read_only'
)
ORDER BY section, metric;
