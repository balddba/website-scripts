/*******************************************************************************
*
* Script Name: database_sizes.sql
* Title: Database and schema sizes
* Tags: Capacity, Storage, System
* Purpose: Reports storage space consumed by each database schema
*
* Description:
*   Aggregates table data and index sizes across all database schemas in the
*   instance, reporting total data size, index size, and total footprint in MB/GB.
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT on information_schema.tables
*
* Output Format:
*   - schema_name: Database / schema name
*   - table_count: Number of tables in schema
*   - data_mb: Data size in Megabytes
*   - index_mb: Index size in Megabytes
*   - total_mb: Combined size in Megabytes
*   - total_gb: Combined size in Gigabytes
*
* Example Usage:
*   mysql -u root -p < database_sizes.sql
*   mysql> source database_sizes.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    table_schema AS schema_name,
    COUNT(*) AS table_count,
    ROUND(SUM(COALESCE(data_length, 0)) / 1024 / 1024, 2) AS data_mb,
    ROUND(SUM(COALESCE(index_length, 0)) / 1024 / 1024, 2) AS index_mb,
    ROUND(SUM(COALESCE(data_length + index_length, 0)) / 1024 / 1024, 2) AS total_mb,
    ROUND(SUM(COALESCE(data_length + index_length, 0)) / 1024 / 1024 / 1024, 3) AS total_gb
FROM information_schema.tables
WHERE table_schema NOT IN ('information_schema', 'performance_schema', 'sys')
GROUP BY table_schema
ORDER BY total_mb DESC;
