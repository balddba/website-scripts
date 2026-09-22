/*******************************************************************************
*
* Script Name: innodb_buffer_pool.sql
* Title: InnoDB buffer pool statistics and hit ratio
* Tags: InnoDB, Memory, Performance
* Purpose: Reports InnoDB buffer pool sizing, page distribution, and cache hit ratio
*
* Description:
*   Inspects InnoDB buffer pool status to show total memory allocated, instance
*   count, distribution of data, free, and dirty pages, and the logical read
*   cache hit ratio.
*
* Parameters:
*   None
*
* Required Privileges:
*   - PROCESS (or SELECT on performance_schema.global_status / global_variables)
*
* Output Format:
*   - metric: Buffer pool metric name
*   - value: Formatted value or percentage
*
* Example Usage:
*   mysql -u root -p < innodb_buffer_pool.sql
*   mysql> source innodb_buffer_pool.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    'Buffer Pool Size' AS metric,
    CONCAT(ROUND(@@innodb_buffer_pool_size / 1024 / 1024 / 1024, 2), ' GB (', ROUND(@@innodb_buffer_pool_size / 1024 / 1024, 0), ' MB)') AS value
UNION ALL
SELECT
    'Buffer Pool Instances',
    CAST(@@innodb_buffer_pool_instances AS CHAR)
UNION ALL
SELECT
    'Buffer Pool Page Size',
    CONCAT(ROUND(@@innodb_page_size / 1024, 0), ' KB')
UNION ALL
SELECT
    'Total Pages',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_total'
UNION ALL
SELECT
    'Data Pages',
    CONCAT(
        VARIABLE_VALUE, ' (',
        ROUND(CAST(VARIABLE_VALUE AS DECIMAL(12, 2)) / NULLIF(
            (SELECT CAST(VARIABLE_VALUE AS DECIMAL(12, 2)) FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_total'), 0
        ) * 100, 2), '%)'
    )
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_data'
UNION ALL
SELECT
    'Free Pages',
    CONCAT(
        VARIABLE_VALUE, ' (',
        ROUND(CAST(VARIABLE_VALUE AS DECIMAL(12, 2)) / NULLIF(
            (SELECT CAST(VARIABLE_VALUE AS DECIMAL(12, 2)) FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_total'), 0
        ) * 100, 2), '%)'
    )
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_free'
UNION ALL
SELECT
    'Dirty Pages',
    CONCAT(
        VARIABLE_VALUE, ' (',
        ROUND(CAST(VARIABLE_VALUE AS DECIMAL(12, 2)) / NULLIF(
            (SELECT CAST(VARIABLE_VALUE AS DECIMAL(12, 2)) FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_total'), 0
        ) * 100, 2), '%)'
    )
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_buffer_pool_pages_dirty'
UNION ALL
SELECT
    'Logical Read Requests',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_buffer_pool_read_requests'
UNION ALL
SELECT
    'Disk Physical Reads',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Innodb_buffer_pool_reads'
UNION ALL
SELECT
    'Buffer Pool Hit Ratio',
    CONCAT(
        ROUND(
            (1 - (
                (SELECT CAST(VARIABLE_VALUE AS DECIMAL(20, 2)) FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_reads') /
                NULLIF((SELECT CAST(VARIABLE_VALUE AS DECIMAL(20, 2)) FROM performance_schema.global_status WHERE VARIABLE_NAME = 'Innodb_buffer_pool_read_requests'), 0)
            )) * 100,
            4
        ),
        '%'
    );
