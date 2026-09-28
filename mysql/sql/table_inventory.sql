/*******************************************************************************
*
* Script Name: table_inventory.sql
* Title: Table inventory with storage engines
* Tags: Tables, Metadata, Storage
* Purpose: Shows tables with basic metadata including storage engine and size
*
* Description:
*   Lists user tables and views across the instance with table type, storage
*   engine, row format, estimated rows, storage footprint, timestamps, and
*   collation.
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT on information_schema.tables
*
* Output Format:
*   - schema_name: Schema containing the object
*   - table_name: Table or view name
*   - table_type: BASE TABLE, VIEW, or system-specific type
*   - engine: Storage engine, or VIEW when not applicable
*   - row_format: Physical row format when available
*   - est_rows: Optimizer-estimated row count
*   - data_mb: Data size in MB
*   - index_mb: Index size in MB
*   - create_time: Object creation timestamp
*   - update_time: Last update timestamp when tracked
*   - table_collation: Table collation when available
*
* Example Usage:
*   mysql -u root -p < table_inventory.sql
*   mysql> source table_inventory.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    table_schema AS schema_name,
    table_name,
    table_type,
    COALESCE(engine, 'VIEW') AS engine,
    COALESCE(row_format, 'N/A') AS row_format,
    COALESCE(table_rows, 0) AS est_rows,
    ROUND(COALESCE(data_length, 0) / 1024 / 1024, 2) AS data_mb,
    ROUND(COALESCE(index_length, 0) / 1024 / 1024, 2) AS index_mb,
    create_time,
    update_time,
    COALESCE(table_collation, 'N/A') AS table_collation
FROM information_schema.tables
WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
ORDER BY table_schema, table_name;
