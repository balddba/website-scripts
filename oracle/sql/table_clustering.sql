/*******************************************************************************
*
* Script Name: table_clustering.sql
* Title: Table clustering statistics
* Tags: Performance, Indexes, Statistics
* Purpose: Report index clustering factor, table storage order, and attribute clustering for one table
*
* Description:
*   Clustering factor is an index statistic: how well table row order matches
*   that index. Values near table blocks mean range scans stay in the same
*   data blocks. Values near row count mean rows are scattered and range scans
*   do more random I/O. Rebuilding an index does not change clustering factor;
*   the table itself must be reordered (attribute clustering, redefinition, or
*   a ordered recreate). Bitmap and domain indexes are not assessed. TABLE
*   CACHED BLOCKS changes how DBMS_STATS counts clustering factor. Attribute
*   clustering and zone maps require Oracle 12c or later.
*
* Parameters:
*   &1 - Required table name in OWNER.TABLE_NAME format
*
* Required Privileges:
*   - SELECT on DBA_TABLES
*   - SELECT on DBA_TAB_STATISTICS
*   - SELECT on DBA_INDEXES
*   - SELECT on DBA_IND_COLUMNS
*   - SELECT on DBA_IND_PARTITIONS
*   - SELECT on DBA_TAB_PARTITIONS
*   - SELECT on DBA_PART_INDEXES
*   - SELECT on DBA_CLUSTERING_TABLES
*   - SELECT on DBA_CLUSTERING_KEYS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Table row, block, IOT, cluster, and statistics-preference context
*   - One row per index with clustering factor, CF/blocks, and quality
*   - Local index partitions compared to matching table partitions
*   - Attribute clustering definition and key columns when present
*
* Example Usage:
*   @table_clustering HR.EMPLOYEES
*   @table_clustering SH.SALES
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 220
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF
SET WRAP OFF

VARIABLE object_owner VARCHAR2(128)
VARIABLE object_name  VARCHAR2(128)

DECLARE
    l_target       VARCHAR2(261) := UPPER(TRIM('&1'));
    l_dot_position PLS_INTEGER;
    l_table_count  PLS_INTEGER;
BEGIN
    -- Parse and validate the required OWNER.TABLE_NAME argument.
    l_dot_position := INSTR(l_target, '.');
    IF l_dot_position <= 1
       OR l_dot_position = LENGTH(l_target)
       OR INSTR(l_target, '.', l_dot_position + 1) > 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Object must be in OWNER.TABLE_NAME format.'
        );
    END IF;

    :object_owner := SUBSTR(l_target, 1, l_dot_position - 1);
    :object_name  := SUBSTR(l_target, l_dot_position + 1);

    -- This interface intentionally supports ordinary, unquoted identifiers.
    IF NOT REGEXP_LIKE(:object_owner, '^[A-Z][A-Z0-9_$#]*$')
       OR NOT REGEXP_LIKE(:object_name, '^[A-Z][A-Z0-9_$#]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Owner and table must be ordinary Oracle identifiers.'
        );
    END IF;

    SELECT COUNT(*)
    INTO l_table_count
    FROM dba_tables
    WHERE owner = :object_owner
      AND table_name = :object_name;

    IF l_table_count = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'Table ' || :object_owner || '.' || :object_name || ' was not found.'
        );
    END IF;
END;
/

COLUMN property FORMAT A28 HEADING 'Property'
COLUMN value    FORMAT A80 HEADING 'Value'

PROMPT
PROMPT === Table clustering context ===
PROMPT

WITH table_details AS (
    SELECT
        t.owner,
        t.table_name,
        t.partitioned,
        t.iot_type,
        t.cluster_name,
        t.num_rows,
        t.blocks,
        t.empty_blocks,
        t.avg_row_len,
        t.chain_cnt,
        t.last_analyzed,
        s.stale_stats,
        DBMS_STATS.GET_PREFS(
            'TABLE_CACHED_BLOCKS',
            t.owner,
            t.table_name
        ) AS table_cached_blocks
    FROM dba_tables t
    LEFT JOIN dba_tab_statistics s
      ON s.owner = t.owner
     AND s.table_name = t.table_name
     AND s.partition_name IS NULL
    WHERE t.owner = :object_owner
      AND t.table_name = :object_name
)
SELECT property, value
FROM (
    SELECT 1 AS sort_order, 'Owner' AS property, owner AS value
    FROM table_details
    UNION ALL
    SELECT 2, 'Table name', table_name FROM table_details
    UNION ALL
    SELECT 3, 'Partitioned', partitioned FROM table_details
    UNION ALL
    SELECT 4, 'IOT type', NVL(iot_type, '(heap table)') FROM table_details
    UNION ALL
    SELECT 5, 'Table cluster', NVL(cluster_name, '(none)') FROM table_details
    UNION ALL
    SELECT 6, 'Estimated rows',
           NVL(TO_CHAR(num_rows, 'FM999G999G999G999G990'), '(not gathered)')
    FROM table_details
    UNION ALL
    SELECT 7, 'Blocks',
           NVL(TO_CHAR(blocks, 'FM999G999G999G999G990'), '(not gathered)')
    FROM table_details
    UNION ALL
    SELECT 8, 'Empty blocks',
           NVL(TO_CHAR(empty_blocks, 'FM999G999G999G999G990'), '(not gathered)')
    FROM table_details
    UNION ALL
    SELECT 9, 'Average row length',
           NVL(TO_CHAR(avg_row_len, 'FM999G999G999G999G990'), '(not gathered)')
    FROM table_details
    UNION ALL
    SELECT 10, 'Chained rows',
           NVL(TO_CHAR(chain_cnt, 'FM999G999G999G999G990'), '(not gathered)')
    FROM table_details
    UNION ALL
    SELECT 11, 'Last analyzed',
           NVL(TO_CHAR(last_analyzed, 'YYYY-MM-DD HH24:MI:SS'), '(not gathered)')
    FROM table_details
    UNION ALL
    SELECT 12, 'Stale statistics', NVL(stale_stats, 'UNKNOWN')
    FROM table_details
    UNION ALL
    SELECT 13, 'TABLE_CACHED_BLOCKS', NVL(table_cached_blocks, '(default)')
    FROM table_details
)
ORDER BY sort_order;

COLUMN index_name        FORMAT A28 HEADING 'Index'
COLUMN index_type        FORMAT A22 HEADING 'Type'
COLUMN uniqueness        FORMAT A7  HEADING 'Unique'
COLUMN index_columns     FORMAT A40 HEADING 'Columns'
COLUMN clustering_factor FORMAT 999,999,999,999 HEADING 'Clust Factor'
COLUMN table_blocks      FORMAT 999,999,999 HEADING 'Tab Blocks'
COLUMN table_rows        FORMAT 999,999,999,999 HEADING 'Tab Rows'
COLUMN cf_per_block      FORMAT 9990.00 HEADING 'CF/Blocks'
COLUMN avg_data_blks     FORMAT 999,999,990 HEADING 'Avg Data Blks/Key'
COLUMN quality           FORMAT A8  HEADING 'Quality'
COLUMN index_analyzed    FORMAT A19 HEADING 'Index Analyzed'

PROMPT
PROMPT === Index clustering factor ===
PROMPT Quality: GOOD = CF within 2x of table blocks (storage matches index
PROMPT order). FAIR = mixed. POOR = CF near row count (scattered rows).
PROMPT N/A = bitmap or domain index. Rebuilds do not improve CF.
PROMPT

WITH index_columns AS (
    SELECT
        index_owner,
        index_name,
        LISTAGG(column_name, ', ') WITHIN GROUP (ORDER BY column_position)
            AS index_columns
    FROM dba_ind_columns
    WHERE table_owner = :object_owner
      AND table_name = :object_name
    GROUP BY index_owner, index_name
),
index_stats AS (
    SELECT
        i.index_name,
        i.index_type,
        i.uniqueness,
        c.index_columns,
        i.clustering_factor,
        t.blocks AS table_blocks,
        t.num_rows AS table_rows,
        ROUND(i.clustering_factor / NULLIF(t.blocks, 0), 2) AS cf_per_block,
        i.avg_data_blocks_per_key AS avg_data_blks,
        CASE
            WHEN i.clustering_factor IS NULL
              OR t.num_rows IS NULL
              OR t.blocks IS NULL
                THEN 'NO STATS'
            WHEN t.num_rows = 0
                THEN 'EMPTY'
            WHEN i.index_type LIKE '%BITMAP%'
              OR i.index_type LIKE '%DOMAIN%'
                THEN 'N/A'
            WHEN i.clustering_factor <= t.blocks * 2
                THEN 'GOOD'
            WHEN i.clustering_factor >= t.num_rows * 0.8
                THEN 'POOR'
            ELSE 'FAIR'
        END AS quality,
        TO_CHAR(i.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS index_analyzed
    FROM dba_indexes i
    JOIN dba_tables t
      ON t.owner = i.table_owner
     AND t.table_name = i.table_name
    LEFT JOIN index_columns c
      ON c.index_owner = i.owner
     AND c.index_name = i.index_name
    WHERE i.table_owner = :object_owner
      AND i.table_name = :object_name
)
SELECT
    index_name,
    index_type,
    uniqueness,
    index_columns,
    clustering_factor,
    table_blocks,
    table_rows,
    cf_per_block,
    avg_data_blks,
    quality,
    index_analyzed
FROM index_stats
ORDER BY
    CASE quality
        WHEN 'POOR' THEN 1
        WHEN 'FAIR' THEN 2
        WHEN 'GOOD' THEN 3
        WHEN 'N/A' THEN 4
        ELSE 5
    END,
    cf_per_block DESC NULLS LAST,
    index_name;

COLUMN partition_name    FORMAT A30 HEADING 'Partition'
COLUMN locality          FORMAT A6  HEADING 'Local?'
COLUMN part_cf           FORMAT 999,999,999,999 HEADING 'Clust Factor'
COLUMN part_blocks       FORMAT 999,999,999 HEADING 'Part Blocks'
COLUMN part_rows         FORMAT 999,999,999,999 HEADING 'Part Rows'
COLUMN part_cf_per_block FORMAT 9990.00 HEADING 'CF/Blocks'
COLUMN part_quality      FORMAT A8  HEADING 'Quality'
COLUMN part_analyzed     FORMAT A19 HEADING 'Index Analyzed'

PROMPT
PROMPT === Local index partition clustering ===
PROMPT Compared to the matching table partition. Global partitioned indexes
PROMPT are listed without a quality score. Empty when the table is not
PROMPT partitioned.
PROMPT

WITH part_stats AS (
    SELECT
        i.index_name,
        ip.partition_name,
        NVL(pi.locality, 'GLOBAL') AS locality,
        ip.clustering_factor AS part_cf,
        tp.blocks AS part_blocks,
        tp.num_rows AS part_rows,
        ROUND(
            ip.clustering_factor / NULLIF(tp.blocks, 0),
            2
        ) AS part_cf_per_block,
        CASE
            WHEN NVL(pi.locality, 'GLOBAL') <> 'LOCAL'
                THEN 'N/A'
            WHEN ip.clustering_factor IS NULL
              OR tp.num_rows IS NULL
              OR tp.blocks IS NULL
                THEN 'NO STATS'
            WHEN tp.num_rows = 0
                THEN 'EMPTY'
            WHEN i.index_type LIKE '%BITMAP%'
              OR i.index_type LIKE '%DOMAIN%'
                THEN 'N/A'
            WHEN ip.clustering_factor <= tp.blocks * 2
                THEN 'GOOD'
            WHEN ip.clustering_factor >= tp.num_rows * 0.8
                THEN 'POOR'
            ELSE 'FAIR'
        END AS part_quality,
        TO_CHAR(ip.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS part_analyzed
    FROM dba_indexes i
    JOIN dba_ind_partitions ip
      ON ip.index_owner = i.owner
     AND ip.index_name = i.index_name
    LEFT JOIN dba_part_indexes pi
      ON pi.owner = i.owner
     AND pi.index_name = i.index_name
    LEFT JOIN dba_tab_partitions tp
      ON tp.table_owner = i.table_owner
     AND tp.table_name = i.table_name
     AND tp.partition_name = ip.partition_name
     AND pi.locality = 'LOCAL'
    WHERE i.table_owner = :object_owner
      AND i.table_name = :object_name
      AND i.partitioned = 'YES'
)
SELECT
    index_name,
    partition_name,
    locality,
    part_cf,
    part_blocks,
    part_rows,
    part_cf_per_block,
    part_quality,
    part_analyzed
FROM part_stats
ORDER BY
    CASE part_quality
        WHEN 'POOR' THEN 1
        WHEN 'FAIR' THEN 2
        WHEN 'GOOD' THEN 3
        WHEN 'N/A' THEN 4
        ELSE 5
    END,
    part_cf_per_block DESC NULLS LAST,
    index_name,
    partition_name;

COLUMN clustering_type     FORMAT A11 HEADING 'Type'
COLUMN on_load             FORMAT A7  HEADING 'On Load'
COLUMN on_datamovement     FORMAT A12 HEADING 'On Data Move'
COLUMN clustering_valid    FORMAT A5  HEADING 'Valid'
COLUMN with_zonemap        FORMAT A8  HEADING 'Zonemap'
COLUMN last_load_clustered FORMAT A19 HEADING 'Last Load Clustered'
COLUMN last_move_clustered FORMAT A19 HEADING 'Last Move Clustered'

PROMPT
PROMPT === Attribute clustering ===
PROMPT Empty when the table has no CLUSTERING clause (12c or later).
PROMPT

SELECT
    ct.clustering_type,
    ct.on_load,
    ct.on_datamovement,
    ct.valid AS clustering_valid,
    ct.with_zonemap,
    TO_CHAR(ct.last_load_clst, 'YYYY-MM-DD HH24:MI:SS') AS last_load_clustered,
    TO_CHAR(ct.last_datamove_clst, 'YYYY-MM-DD HH24:MI:SS') AS last_move_clustered
FROM dba_clustering_tables ct
WHERE ct.owner = :object_owner
  AND ct.table_name = :object_name;

COLUMN groupid        FORMAT 9990 HEADING 'Group'
COLUMN position       FORMAT 9990 HEADING 'Pos'
COLUMN detail_owner   FORMAT A20 HEADING 'Detail Owner'
COLUMN detail_name    FORMAT A30 HEADING 'Detail Table'
COLUMN detail_column  FORMAT A30 HEADING 'Column'

PROMPT
PROMPT === Attribute clustering keys ===
PROMPT

SELECT
    ck.groupid,
    ck.position,
    ck.detail_owner,
    ck.detail_name,
    ck.detail_column
FROM dba_clustering_keys ck
WHERE ck.owner = :object_owner
  AND ck.table_name = :object_name
ORDER BY ck.groupid, ck.position;
