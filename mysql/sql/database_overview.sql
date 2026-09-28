/*******************************************************************************
*
* Script Name: database_overview.sql
* Title: Database overview
* Tags: Databases, Metadata, Storage
* Purpose: Shows databases with basic charset, collation, object, and storage information
*
* Description:
*   Reports every non-system database with default character set, default
*   collation, object counts, approximate storage, and default encryption setting
*   when the server exposes it.
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT on information_schema.schemata
*   - SELECT on information_schema.tables
*
* Output Format:
*   - schema_name: Database / schema name
*   - default_character_set: Schema default character set
*   - default_collation: Schema default collation
*   - table_count: Total tables and views
*   - base_tables: Base table count
*   - views: View count
*   - total_mb: Approximate data plus index size in MB
*   - default_encryption: Schema default encryption flag, when available
*
* Example Usage:
*   mysql -u root -p < database_overview.sql
*   mysql> source database_overview.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    s.schema_name,
    s.default_character_set_name AS default_character_set,
    s.default_collation_name AS default_collation,
    COUNT(t.table_name) AS table_count,
    SUM(CASE WHEN t.table_type = 'BASE TABLE' THEN 1 ELSE 0 END) AS base_tables,
    SUM(CASE WHEN t.table_type = 'VIEW' THEN 1 ELSE 0 END) AS views,
    ROUND(SUM(COALESCE(t.data_length, 0) + COALESCE(t.index_length, 0)) / 1024 / 1024, 2) AS total_mb,
    COALESCE(s.default_encryption, 'N/A') AS default_encryption
FROM information_schema.schemata AS s
LEFT JOIN information_schema.tables AS t
    ON t.table_schema = s.schema_name
WHERE s.schema_name NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
GROUP BY
    s.schema_name,
    s.default_character_set_name,
    s.default_collation_name,
    s.default_encryption
ORDER BY s.schema_name;
