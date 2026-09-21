/*******************************************************************************
*
* Script Name: stale_stats.sql
* Title: Stale Optimizer Statistics
* Tags: Optimizer, Statistics, CBO
* Purpose: Reports tables and partitions with stale or missing optimizer statistics from dba_tab_statistics (optional &1 for schema/owner, defaults to '%').
*
* Description:
*   Identifies tables, partitions, and subpartitions where optimizer statistics
*   are marked stale or are missing entirely. Helps database administrators and
*   performance engineers find objects needing statistics gathering.
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
*   - Number of Rows
*   - Blocks
*   - Last Analyzed Timestamp
*   - Stale Stats Flag
*   - Statistics Locked Status
*
* Example Usage:
*   sqlplus user/password@yourdb @stale_stats.sql
*   sqlplus user/password@yourdb @stale_stats.sql HR
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
COLUMN num_rows         FORMAT 999,999,999,990 HEADING 'Num Rows'
COLUMN blocks           FORMAT 999,999,990     HEADING 'Blocks'
COLUMN last_analyzed    FORMAT A19             HEADING 'Last Analyzed'
COLUMN stale_stats      FORMAT A11             HEADING 'Stale Stats'
COLUMN stattype_locked  FORMAT A10             HEADING 'Locked'

SELECT
    owner,
    table_name,
    partition_name,
    object_type,
    num_rows,
    blocks,
    TO_CHAR(last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS last_analyzed,
    stale_stats,
    stattype_locked
FROM dba_tab_statistics
WHERE owner LIKE UPPER(NVL(NULLIF(CAST(TRIM('&1') AS VARCHAR2(128)), ''), '%'))
  AND (stale_stats = 'YES' OR last_analyzed IS NULL)
  AND table_name NOT LIKE 'BIN$%'
ORDER BY owner, table_name, object_type, partition_name;
