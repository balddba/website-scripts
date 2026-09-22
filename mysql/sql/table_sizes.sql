/*******************************************************************************
*
* Script Name: table_sizes.sql
* Title: Top tables by storage size
* Tags: Capacity, Storage, Tables
* Purpose: Reports largest tables in the instance with data and index sizes
*
* Description:
*   Lists the top 50 largest tables across user schemas, including storage engine,
*   estimated row count, data size, index size, and total footprint in MB.
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT on information_schema.tables
*
* Output Format:
*   - schema_name: Schema containing the table
*   - table_name: Name of the table
*   - engine: Storage engine (InnoDB, MyISAM, etc.)
*   - est_rows: Estimated row count
*   - data_mb: Data size in MB
*   - index_mb: Index size in MB
*   - total_mb: Total size in MB
*   - row_format: Row format (Dynamic, Compact, Compressed)
*
* Example Usage:
*   mysql -u root -p < table_sizes.sql
*   mysql> source table_sizes.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    table_schema AS schema_name,
    table_name,
    COALESCE(engine, 'VIEW') AS engine,
    COALESCE(table_rows, 0) AS est_rows,
    ROUND(COALESCE(data_length, 0) / 1024 / 1024, 2) AS data_mb,
    ROUND(COALESCE(index_length, 0) / 1024 / 1024, 2) AS index_mb,
    ROUND(COALESCE(data_length + index_length, 0) / 1024 / 1024, 2) AS total_mb,
    COALESCE(row_format, 'N/A') AS row_format
FROM information_schema.tables
WHERE table_schema NOT IN ('information_schema', 'performance_schema', 'sys')
ORDER BY (COALESCE(data_length, 0) + COALESCE(index_length, 0)) DESC
LIMIT 50;
