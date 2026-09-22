/*******************************************************************************
*
* Script Name: unused_indexes.sql
* Title: Unused schema indexes
* Tags: Indexes, Performance, Schema
* Purpose: Identifies secondary indexes that have received zero read/lookup operations
*
* Description:
*   Queries sys.schema_unused_indexes to find redundant or unused secondary
*   indexes across user databases since the last server restart or stats reset.
*   Unused indexes consume storage and slow down DML operations (INSERT, UPDATE, DELETE).
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT on sys.schema_unused_indexes
*
* Output Format:
*   - schema_name: Schema containing the table
*   - table_name: Table name
*   - index_name: Name of the unused index
*
* Example Usage:
*   mysql -u root -p < unused_indexes.sql
*   mysql> source unused_indexes.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    object_schema AS schema_name,
    object_name AS table_name,
    index_name
FROM sys.schema_unused_indexes
WHERE object_schema NOT IN ('information_schema', 'performance_schema', 'sys', 'mysql')
ORDER BY object_schema, object_name, index_name;
