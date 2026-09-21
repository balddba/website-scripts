/*******************************************************************************
*
* Script Name: stats_history.sql
* Title: Statistics Modification History
* Tags: Optimizer, Statistics
* Purpose: Displays past statistics collection timestamps and history from dba_tab_stats_history (optional &1 for table name, defaults to '%').
*
* Description:
*   Queries the statistics history retention repository (DBA_TAB_STATS_HISTORY)
*   to show historical statistics collection and modification timestamps for
*   tables and partitions.
*
* Parameters:
*   &1 - (Optional) Table name filter. Default: % (all tables)
*
* Required Privileges:
*   - SELECT on DBA_TAB_STATS_HISTORY
*
* Output Format:
*   - Owner
*   - Table Name
*   - Partition Name
*   - Subpartition Name
*   - Statistics Update Timestamp
*
* Example Usage:
*   sqlplus user/password@yourdb @stats_history.sql
*   sqlplus user/password@yourdb @stats_history.sql EMPLOYEES
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET LINESIZE 200
SET PAGESIZE 100
SET VERIFY OFF

COLUMN owner             FORMAT A20 HEADING 'Owner'
COLUMN table_name        FORMAT A30 HEADING 'Table Name'
COLUMN partition_name    FORMAT A25 HEADING 'Partition Name'
COLUMN subpartition_name FORMAT A25 HEADING 'Subpartition Name'
COLUMN stats_update_time FORMAT A35 HEADING 'Stats Update Time'

SELECT
    owner,
    table_name,
    partition_name,
    subpartition_name,
    TO_CHAR(stats_update_time, 'YYYY-MM-DD HH24:MI:SS TZR') AS stats_update_time
FROM dba_tab_stats_history
WHERE table_name LIKE UPPER(NVL(NULLIF(CAST(TRIM('&1') AS VARCHAR2(128)), ''), '%'))
  AND table_name NOT LIKE 'BIN$%'
ORDER BY stats_update_time DESC, owner, table_name, partition_name, subpartition_name;
