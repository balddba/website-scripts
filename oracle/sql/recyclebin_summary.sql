/*******************************************************************************
*
* Script Name: recyclebin_summary.sql
* Title: Recyclebin Space Summary
* Tags: Storage, Recyclebin, Space
* Purpose: Summarizes space occupied by dropped objects in dba_recyclebin per owner and tablespace.
*
* Description:
*   Summarizes the space consumed by dropped objects residing in the Oracle
*   Recycle Bin across all schemas and tablespaces. Aggregates object count,
*   table count, index count, total blocks, and total space (MB and GB) from
*   DBA_RECYCLEBIN grouped by owner and tablespace name. Useful for evaluating
*   space reclamation potential prior to executing PURGE RECYCLEBIN or PURGE
*   DBA_RECYCLEBIN.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on DBA_RECYCLEBIN
*   - SELECT on DBA_TABLESPACES
*
* Output Format:
*   - Owner (Schema)
*   - Tablespace Name
*   - Total Object Count, Table Count, and Index Count
*   - Total Blocks
*   - Space Occupied in MB and GB
*   - Summary Totals
*
* Example Usage:
*   sqlplus user/password@yourdb @recyclebin_summary.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 200
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN owner           FORMAT A24            HEADING 'Owner'
COLUMN tablespace_name FORMAT A24            HEADING 'Tablespace'
COLUMN object_count    FORMAT 999,990        HEADING 'Objects'
COLUMN table_count     FORMAT 999,990        HEADING 'Tables'
COLUMN index_count     FORMAT 999,990        HEADING 'Indexes'
COLUMN total_blocks    FORMAT 999,999,990    HEADING 'Total Blocks'
COLUMN space_mb        FORMAT 999,990.00     HEADING 'Space MB'
COLUMN space_gb        FORMAT 999,990.000    HEADING 'Space GB'

BREAK ON REPORT
COMPUTE SUM OF object_count table_count index_count total_blocks space_mb space_gb ON REPORT

PROMPT
PROMPT === Recyclebin Space Summary ===
PROMPT

SELECT
    r.owner,
    NVL(r.ts_name, '(none)') AS tablespace_name,
    COUNT(*) AS object_count,
    SUM(CASE WHEN r.type = 'TABLE' THEN 1 ELSE 0 END) AS table_count,
    SUM(CASE WHEN r.type = 'INDEX' THEN 1 ELSE 0 END) AS index_count,
    SUM(r.space) AS total_blocks,
    ROUND(SUM(r.space * NVL(ts.block_size, 8192)) / 1024 / 1024, 2) AS space_mb,
    ROUND(SUM(r.space * NVL(ts.block_size, 8192)) / 1024 / 1024 / 1024, 3) AS space_gb
FROM dba_recyclebin r
LEFT JOIN dba_tablespaces ts
  ON ts.tablespace_name = r.ts_name
GROUP BY r.owner, r.ts_name
ORDER BY space_mb DESC, r.owner, r.ts_name;

COLUMN owner CLEAR
COLUMN tablespace_name CLEAR
COLUMN object_count CLEAR
COLUMN table_count CLEAR
COLUMN index_count CLEAR
COLUMN total_blocks CLEAR
COLUMN space_mb CLEAR
COLUMN space_gb CLEAR

CLEAR BREAKS
CLEAR COMPUTES

SET FEEDBACK ON
