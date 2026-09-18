/*******************************************************************************
*
* Script Name: tablespace_usage.sql
* Title: Tablespace usage
* Tags: Capacity, Tablespaces
* Purpose: Display tablespace used, free space, and percent full for capacity checks
*
* Description:
*   Summarizes datafile size, free space, and percent used per tablespace.
*   Output is sorted by percentage used in descending order.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on DBA_DATA_FILES
*   - SELECT on DBA_FREE_SPACE
*
* Output Format:
*   - Tablespace name
*   - Size in MB
*   - Free space in MB
*   - Percent used
*
* Example Usage:
*   sqlplus user/password@yourdb @tablespace_usage.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    df.tablespace_name,
    ROUND(df.bytes / 1024 / 1024) AS size_mb,
    ROUND(NVL(fs.free_bytes, 0) / 1024 / 1024) AS free_mb,
    ROUND((df.bytes - NVL(fs.free_bytes, 0)) / df.bytes * 100, 1) AS pct_used
FROM (
    SELECT tablespace_name, SUM(bytes) AS bytes
    FROM dba_data_files
    GROUP BY tablespace_name
) df
LEFT JOIN (
    SELECT tablespace_name, SUM(bytes) AS free_bytes
    FROM dba_free_space
    GROUP BY tablespace_name
) fs ON df.tablespace_name = fs.tablespace_name
ORDER BY pct_used DESC;
