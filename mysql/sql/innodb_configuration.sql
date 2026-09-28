/*******************************************************************************
*
* Script Name: innodb_configuration.sql
* Title: InnoDB configuration
* Tags: InnoDB, Configuration
* Purpose: Displays important InnoDB configuration variables
*
* Description:
*   Reports key InnoDB server variables grouped into practical categories for
*   buffer pool, redo logging, flushing, I/O, locking, and durability review.
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT on performance_schema.global_variables
*
* Output Format:
*   - variable_name: InnoDB server variable name
*   - variable_value: Current global value
*   - category: Configuration area
*
* Example Usage:
*   mysql -u root -p < innodb_configuration.sql
*   mysql> source innodb_configuration.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    variable_name,
    variable_value,
    CASE
        WHEN variable_name LIKE 'innodb_buffer_pool%' THEN 'Buffer Pool'
        WHEN variable_name LIKE 'innodb_log%' OR variable_name LIKE 'innodb_redo%' OR variable_name LIKE 'innodb_flush_log%' THEN 'Redo and Durability'
        WHEN variable_name LIKE 'innodb_io%' OR variable_name LIKE 'innodb_read_io%' OR variable_name LIKE 'innodb_write_io%' OR variable_name LIKE 'innodb_flush%' THEN 'I/O and Flushing'
        WHEN variable_name LIKE 'innodb_lock%' OR variable_name LIKE 'innodb_deadlock%' THEN 'Locking'
        WHEN variable_name LIKE 'innodb_temp%' OR variable_name LIKE 'innodb_undo%' THEN 'Temporary and Undo'
        ELSE 'General'
    END AS category
FROM performance_schema.global_variables
WHERE variable_name IN (
    'innodb_buffer_pool_size',
    'innodb_buffer_pool_instances',
    'innodb_buffer_pool_chunk_size',
    'innodb_log_file_size',
    'innodb_log_files_in_group',
    'innodb_redo_log_capacity',
    'innodb_flush_log_at_trx_commit',
    'innodb_flush_method',
    'innodb_flush_neighbors',
    'innodb_io_capacity',
    'innodb_io_capacity_max',
    'innodb_read_io_threads',
    'innodb_write_io_threads',
    'innodb_lock_wait_timeout',
    'innodb_deadlock_detect',
    'innodb_file_per_table',
    'innodb_temp_data_file_path',
    'innodb_undo_tablespaces',
    'innodb_autoinc_lock_mode',
    'innodb_stats_persistent'
)
ORDER BY category, variable_name;
