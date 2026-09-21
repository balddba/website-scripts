/*******************************************************************************
*
* Script Name: table_fragmentation.sql
* Title: Table Space Fragmentation
* Tags: Storage, Space, Tables
* Purpose: Estimates table High Water Mark (HWM) space waste and suggests candidates for shrink/rebuild comparing dba_tables and dba_segments (optional &1 for schema/owner, defaults to '%').
*
* Description:
*   Estimates table space waste by comparing allocated segment space in
*   DBA_SEGMENTS against estimated actual data size (NUM_ROWS * AVG_ROW_LEN)
*   from DBA_TABLES. Identifies tables with significant unused space above or
*   below the High Water Mark (HWM) that could benefit from ALTER TABLE
*   SHRINK SPACE or table move/rebuild operations. Supports an optional schema
*   filter.
*
* Parameters:
*   &1 - (Optional) Schema owner. Default is % (all schemas).
*
* Required Privileges:
*   - SELECT on DBA_TABLES
*   - SELECT on DBA_SEGMENTS
*
* Output Format:
*   - Owner and Table Name
*   - Tablespace Name
*   - Number of Rows and Average Row Length
*   - Allocated Space (MB)
*   - Estimated Data Size (MB)
*   - Estimated Wasted Space (MB) and Wasted Percentage
*   - Last Analyzed Date
*
* Example Usage:
*   sqlplus user/password@yourdb @table_fragmentation.sql
*   sqlplus user/password@yourdb @table_fragmentation.sql HR
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

COLUMN c_owner NEW_VALUE p_owner NOPRINT
SELECT NVL(NULLIF(TRIM('&1'), ''), '%') AS c_owner FROM dual;

COLUMN owner           FORMAT A20            HEADING 'Owner'
COLUMN table_name      FORMAT A30            HEADING 'Table Name'
COLUMN tablespace_name FORMAT A20            HEADING 'Tablespace'
COLUMN num_rows        FORMAT 999,999,990    HEADING 'Num Rows'
COLUMN avg_row_len     FORMAT 999,990        HEADING 'Avg Row'
COLUMN allocated_mb    FORMAT 999,990.00     HEADING 'Alloc MB'
COLUMN est_data_mb     FORMAT 999,990.00     HEADING 'Est Data MB'
COLUMN wasted_mb       FORMAT 999,990.00     HEADING 'Wasted MB'
COLUMN wasted_pct      FORMAT 990.0          HEADING 'Wasted %'
COLUMN last_analyzed   FORMAT A19            HEADING 'Last Analyzed'

PROMPT
PROMPT === Table Space Fragmentation ===
PROMPT

WITH seg AS (
    SELECT
        owner,
        segment_name AS table_name,
        SUM(bytes) AS allocated_bytes
    FROM dba_segments
    WHERE segment_type LIKE 'TABLE%'
    GROUP BY owner, segment_name
),
tab AS (
    SELECT
        t.owner,
        t.table_name,
        t.tablespace_name,
        t.num_rows,
        t.avg_row_len,
        t.last_analyzed,
        ROUND(NVL(t.num_rows, 0) * NVL(t.avg_row_len, 0)) AS est_data_bytes
    FROM dba_tables t
    WHERE t.table_name NOT LIKE 'BIN$%'
      AND NVL(t.nested, 'NO') = 'NO'
      AND NVL(t.secondary, 'N') <> 'Y'
      AND NVL(t.iot_type, 'HEAP') NOT IN ('IOT_OVERFLOW', 'IOT_MAPPING')
      AND ('&&p_owner' = '%' OR t.owner = UPPER('&&p_owner'))
)
SELECT
    t.owner,
    t.table_name,
    t.tablespace_name,
    t.num_rows,
    t.avg_row_len,
    ROUND(s.allocated_bytes / 1024 / 1024, 2) AS allocated_mb,
    ROUND(t.est_data_bytes / 1024 / 1024, 2) AS est_data_mb,
    ROUND(GREATEST(s.allocated_bytes - t.est_data_bytes, 0) / 1024 / 1024, 2) AS wasted_mb,
    CASE
        WHEN s.allocated_bytes > 0 AND s.allocated_bytes >= t.est_data_bytes
        THEN ROUND((s.allocated_bytes - t.est_data_bytes) / s.allocated_bytes * 100, 1)
        ELSE 0
    END AS wasted_pct,
    TO_CHAR(t.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS last_analyzed
FROM tab t
JOIN seg s
  ON s.owner = t.owner
 AND s.table_name = t.table_name
ORDER BY wasted_mb DESC, allocated_mb DESC, t.owner, t.table_name;

COLUMN owner CLEAR
COLUMN table_name CLEAR
COLUMN tablespace_name CLEAR
COLUMN num_rows CLEAR
COLUMN avg_row_len CLEAR
COLUMN allocated_mb CLEAR
COLUMN est_data_mb CLEAR
COLUMN wasted_mb CLEAR
COLUMN wasted_pct CLEAR
COLUMN last_analyzed CLEAR

UNDEFINE p_owner
UNDEFINE 1

SET FEEDBACK ON
