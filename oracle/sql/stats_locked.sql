/*******************************************************************************
*
* Script Name: stats_locked.sql
* Title: Locked Optimizer Statistics
* Tags: Optimizer, Statistics
* Purpose: Identifies tables and schemas with locked statistics from dba_tab_statistics where stattype_locked IS NOT NULL.
*
* Description:
*   Reports tables, partitions, and subpartitions that have their optimizer
*   statistics locked against automatic or manual gathering (STATTYPE_LOCKED
*   is not null).
*
* Parameters:
*   &1 - (Optional) Schema owner filter. Default: % (all schemas)
*
* Required Privileges:
*   - SELECT on DBA_TAB_STATISTICS
*
* Output Format:
*   - Owner
*   - Table Name
*   - Partition Name
*   - Object Type
*   - Lock Type (ALL/DATA/CACHE)
*   - Stale Stats Flag
*   - Number of Rows
*   - Blocks
*   - Last Analyzed Timestamp
*
* Example Usage:
*   sqlplus user/password@yourdb @stats_locked.sql
*   sqlplus user/password@yourdb @stats_locked.sql HR
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET LINESIZE 200
SET PAGESIZE 100
SET VERIFY OFF

COLUMN owner            FORMAT A20             HEADING 'Owner'
COLUMN table_name       FORMAT A30             HEADING 'Table Name'
COLUMN partition_name   FORMAT A25             HEADING 'Partition Name'
COLUMN object_type      FORMAT A12             HEADING 'Object Type'
COLUMN stattype_locked  FORMAT A12             HEADING 'Locked Type'
COLUMN stale_stats      FORMAT A11             HEADING 'Stale Stats'
COLUMN num_rows         FORMAT 999,999,999,990 HEADING 'Num Rows'
COLUMN blocks           FORMAT 999,999,990     HEADING 'Blocks'
COLUMN last_analyzed    FORMAT A19             HEADING 'Last Analyzed'

SELECT
    owner,
    table_name,
    partition_name,
    object_type,
    stattype_locked,
    stale_stats,
    num_rows,
    blocks,
    TO_CHAR(last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS last_analyzed
FROM dba_tab_statistics
WHERE stattype_locked IS NOT NULL
  AND owner LIKE UPPER(NVL(NULLIF(CAST(TRIM('&1') AS VARCHAR2(128)), ''), '%'))
  AND table_name NOT LIKE 'BIN$%'
ORDER BY owner, table_name, object_type, partition_name;
