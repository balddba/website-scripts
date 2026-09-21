/*******************************************************************************
*
* Script Name: desc.sql
* Title: Describe an Oracle table
* Tags: Tables, Indexes, Constraints, Statistics
* Purpose: Reports table structure, indexes, constraints, statistics, and size
*
* Description:
*   Produces a read-only description of one Oracle table. The report includes
*   table statistics, allocated segment size, column definitions, indexes and
*   indexed columns, and constraints with their constrained columns.
*
* Parameters:
*   &1 - Required table name in OWNER.TABLE_NAME format
*
* Required Privileges:
*   - SELECT on DBA_TABLES
*   - SELECT on DBA_TAB_COLUMNS
*   - SELECT on DBA_TAB_COLS
*   - SELECT on DBA_TAB_STATISTICS
*   - SELECT on DBA_TAB_MODIFICATIONS
*   - SELECT on DBA_TAB_PARTITIONS
*   - SELECT on DBA_TAB_SUBPARTITIONS
*   - SELECT on DBA_INDEXES
*   - SELECT on DBA_IND_COLUMNS
*   - SELECT on DBA_CONSTRAINTS
*   - SELECT on DBA_CONS_COLUMNS
*   - SELECT on DBA_TRIGGERS
*   - SELECT on DBA_DEPENDENCIES
*   - SELECT on DBA_OBJECTS
*   - SELECT on DBA_LOBS
*   - SELECT on DBA_TAB_COL_STATISTICS
*   - SELECT on DBA_SEGMENTS
*
* Output Format:
*   - Table properties and optimizer statistics
*   - Allocated table, index, and LOB storage
*   - Partition and LOB details
*   - Column definitions
*   - Column statistics and histograms
*   - Index definitions and statistics
*   - Constraint definitions and inbound/outbound foreign-key relationships
*   - Table trigger definitions and status
*   - Views and materialized views that directly reference the table
*   - Object modification statistics
*
* Example Usage:
*   @desc HR.EMPLOYEES
*   @desc APP.ORDERS
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 220
SET PAGESIZE 100
SET LONG 4000
SET LONGCHUNKSIZE 4000
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

COLUMN property FORMAT A22 HEADING 'Property'
COLUMN value    FORMAT A80 HEADING 'Value'

PROMPT
PROMPT === Table summary and statistics ===
PROMPT

WITH table_size AS (
    SELECT NVL(SUM(s.bytes), 0) AS bytes
    FROM dba_segments s
    WHERE s.owner = :object_owner
      AND (
          (s.segment_name = :object_name AND s.segment_type LIKE 'TABLE%')
          OR s.segment_name IN (
                 SELECT i.index_name
                 FROM dba_indexes i
                 WHERE i.owner = s.owner
                   AND i.table_owner = :object_owner
                   AND i.table_name = :object_name
             )
          OR s.segment_name IN (
                 SELECT l.segment_name
                 FROM dba_lobs l
                 WHERE l.owner = :object_owner
                   AND l.table_name = :object_name
                 UNION
                 SELECT l.index_name
                 FROM dba_lobs l
                 WHERE l.owner = :object_owner
                   AND l.table_name = :object_name
             )
      )
),
table_details AS (
    SELECT
        t.owner,
        t.table_name,
        t.tablespace_name,
        t.partitioned,
        t.temporary,
        t.compression,
        t.compress_for,
        t.num_rows,
        t.blocks,
        t.avg_row_len,
        t.sample_size,
        t.last_analyzed,
        s.stale_stats,
        ROUND(sz.bytes / 1024 / 1024, 2) AS total_size_mb
    FROM dba_tables t
    LEFT JOIN dba_tab_statistics s
      ON s.owner = t.owner
     AND s.table_name = t.table_name
     AND s.partition_name IS NULL
    CROSS JOIN table_size sz
    WHERE t.owner = :object_owner
      AND t.table_name = :object_name
),
transposed AS (
    SELECT 1 AS sort_order, 'Owner' AS property, owner AS value
    FROM table_details
    UNION ALL
    SELECT 2, 'Table name', table_name FROM table_details
    UNION ALL
    SELECT 3, 'Tablespace', NVL(tablespace_name, '(none)') FROM table_details
    UNION ALL
    SELECT 4, 'Partitioned', partitioned FROM table_details
    UNION ALL
    SELECT 5, 'Temporary', temporary FROM table_details
    UNION ALL
    SELECT 6, 'Compression', compression FROM table_details
    UNION ALL
    SELECT 7, 'Compress for', NVL(compress_for, '(none)') FROM table_details
    UNION ALL
    -- NUM_ROWS and related values are estimates from the last statistics gather.
    SELECT 8, 'Estimated rows',
           NVL(TO_CHAR(num_rows, 'FM999G999G999G999G990'), '(not gathered)')
    FROM table_details
    UNION ALL
    SELECT 9, 'Blocks',
           NVL(TO_CHAR(blocks, 'FM999G999G999G999G990'), '(not gathered)')
    FROM table_details
    UNION ALL
    SELECT 10, 'Average row length',
           NVL(TO_CHAR(avg_row_len, 'FM999G999G999G999G990'), '(not gathered)')
    FROM table_details
    UNION ALL
    SELECT 11, 'Sample size',
           NVL(TO_CHAR(sample_size, 'FM999G999G999G999G990'), '(not gathered)')
    FROM table_details
    UNION ALL
    SELECT 12, 'Last analyzed',
           NVL(TO_CHAR(last_analyzed, 'YYYY-MM-DD HH24:MI:SS'), '(not gathered)')
    FROM table_details
    UNION ALL
    SELECT 13, 'Stale statistics', NVL(stale_stats, 'UNKNOWN')
    FROM table_details
    UNION ALL
    SELECT 14, 'Total size (MB)',
           TO_CHAR(total_size_mb, 'FM999G999G999G990D00')
    FROM table_details
)
SELECT property, value
FROM transposed
ORDER BY sort_order;

COLUMN segment_category FORMAT A16 HEADING 'Segment Category'
COLUMN size_mb          FORMAT 999,999,990.00 HEADING 'Size MB'

PROMPT
PROMPT === Allocated storage ===
PROMPT

-- Report table, index, and LOB allocation separately for quick comparison.
WITH selected_segments AS (
    SELECT 'TABLE' AS segment_category, s.bytes
    FROM dba_segments s
    WHERE s.owner = :object_owner
      AND s.segment_name = :object_name
      AND s.segment_type LIKE 'TABLE%'
    UNION ALL
    SELECT 'INDEX', s.bytes
    FROM dba_indexes i
    JOIN dba_segments s
      ON s.owner = i.owner
     AND s.segment_name = i.index_name
     AND s.segment_type LIKE 'INDEX%'
    WHERE i.table_owner = :object_owner
      AND i.table_name = :object_name
      AND NOT EXISTS (
              SELECT 1
              FROM dba_lobs l
              WHERE l.owner = i.owner
                AND l.index_name = i.index_name
          )
    UNION ALL
    SELECT 'LOB', s.bytes
    FROM dba_lobs l
    JOIN dba_segments s
      ON s.owner = l.owner
     AND s.segment_name = l.segment_name
    WHERE l.owner = :object_owner
      AND l.table_name = :object_name
    UNION ALL
    SELECT 'LOB INDEX', s.bytes
    FROM dba_lobs l
    JOIN dba_segments s
      ON s.owner = l.owner
     AND s.segment_name = l.index_name
    WHERE l.owner = :object_owner
      AND l.table_name = :object_name
)
SELECT segment_category,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS size_mb
FROM selected_segments
GROUP BY segment_category
UNION ALL
SELECT 'TOTAL',
       ROUND(NVL(SUM(bytes), 0) / 1024 / 1024, 2)
FROM selected_segments
ORDER BY 1;

COLUMN partition_position FORMAT 9990 HEADING 'Pos'
COLUMN partition_name     FORMAT A28
COLUMN tablespace_name     FORMAT A20
COLUMN partition_rows     FORMAT 999,999,999,999 HEADING 'Rows'
COLUMN partition_size_mb  FORMAT 999,999,990.00 HEADING 'Size MB'
COLUMN compression        FORMAT A10
COLUMN compress_for       FORMAT A16 HEADING 'Compress For'
COLUMN partition_analyzed FORMAT A19 HEADING 'Last Analyzed'

PROMPT
PROMPT === Partition details ===
PROMPT

WITH partition_sizes AS (
    SELECT partition_name, SUM(bytes) AS bytes
    FROM (
        SELECT s.partition_name, s.bytes
        FROM dba_segments s
        WHERE s.owner = :object_owner
          AND s.segment_name = :object_name
          AND s.segment_type = 'TABLE PARTITION'
        UNION ALL
        SELECT sp.partition_name, s.bytes
        FROM dba_tab_subpartitions sp
        JOIN dba_segments s
          ON s.owner = sp.table_owner
         AND s.segment_name = sp.table_name
         AND s.partition_name = sp.subpartition_name
         AND s.segment_type = 'TABLE SUBPARTITION'
        WHERE sp.table_owner = :object_owner
          AND sp.table_name = :object_name
    )
    GROUP BY partition_name
)
SELECT
    p.partition_position,
    p.partition_name,
    p.tablespace_name,
    p.num_rows AS partition_rows,
    ROUND(NVL(sz.bytes, 0) / 1024 / 1024, 2) AS partition_size_mb,
    p.compression,
    p.compress_for,
    TO_CHAR(p.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS partition_analyzed
FROM dba_tab_partitions p
LEFT JOIN partition_sizes sz
  ON sz.partition_name = p.partition_name
WHERE p.table_owner = :object_owner
  AND p.table_name = :object_name
ORDER BY p.partition_position;

COLUMN lob_column      FORMAT A25 HEADING 'LOB Column'
COLUMN lob_segment     FORMAT A28 HEADING 'LOB Segment'
COLUMN securefile      FORMAT A10
COLUMN in_row          FORMAT A6  HEADING 'In Row'
COLUMN cache           FORMAT A10
COLUMN logging         FORMAT A10
COLUMN deduplication   FORMAT A10 HEADING 'Dedup'
COLUMN lob_size_mb     FORMAT 999,999,990.00 HEADING 'Size MB'

PROMPT
PROMPT === LOB details ===
PROMPT

WITH lob_sizes AS (
    SELECT segment_name,
           SUM(bytes) AS bytes
    FROM dba_segments
    WHERE owner = :object_owner
      AND segment_type LIKE 'LOB%'
    GROUP BY segment_name
)
SELECT
    l.column_name AS lob_column,
    l.segment_name AS lob_segment,
    l.tablespace_name,
    l.securefile,
    l.in_row,
    l.cache,
    l.logging,
    l.compression,
    l.deduplication,
    ROUND(NVL(sz.bytes, 0) / 1024 / 1024, 2) AS lob_size_mb
FROM dba_lobs l
LEFT JOIN lob_sizes sz
  ON sz.segment_name = l.segment_name
WHERE l.owner = :object_owner
  AND l.table_name = :object_name
ORDER BY l.column_name;

COLUMN column_id       FORMAT 990 HEADING '#'
COLUMN column_name     FORMAT A28
COLUMN data_type       FORMAT A28
COLUMN nullable        FORMAT A8
COLUMN identity_column FORMAT A8 HEADING 'Identity'
COLUMN virtual_column  FORMAT A8 HEADING 'Virtual'
COLUMN data_default    FORMAT A40 TRUNCATED HEADING 'Default (truncated)'

PROMPT
PROMPT === Columns ===
PROMPT

SELECT
    c.column_id,
    c.column_name,
    CASE
        WHEN c.data_type IN ('CHAR', 'VARCHAR2', 'NCHAR', 'NVARCHAR2') THEN
            c.data_type || '(' || c.char_length ||
            CASE c.char_used WHEN 'C' THEN ' CHAR' WHEN 'B' THEN ' BYTE' END || ')'
        WHEN c.data_type = 'NUMBER' AND c.data_precision IS NOT NULL THEN
            c.data_type || '(' || c.data_precision ||
            CASE WHEN c.data_scale IS NOT NULL THEN ',' || c.data_scale END || ')'
        WHEN c.data_type = 'RAW' THEN c.data_type || '(' || c.data_length || ')'
        ELSE c.data_type
    END AS data_type,
    CASE c.nullable WHEN 'Y' THEN 'YES' ELSE 'NO' END AS nullable,
    c.identity_column,
    metadata.virtual_column,
    c.data_default
FROM dba_tab_columns c
LEFT JOIN dba_tab_cols metadata
  ON metadata.owner = c.owner
 AND metadata.table_name = c.table_name
 AND metadata.column_name = c.column_name
WHERE c.owner = :object_owner
  AND c.table_name = :object_name
ORDER BY c.column_id;

COLUMN stats_column     FORMAT A28 HEADING 'Column'
COLUMN num_distinct     FORMAT 999,999,999,999
COLUMN num_nulls        FORMAT 999,999,999,999
COLUMN density          FORMAT 9.9999EEEE
COLUMN num_buckets      FORMAT 999,990 HEADING 'Buckets'
COLUMN histogram        FORMAT A18
COLUMN column_sample    FORMAT 999,999,999,999 HEADING 'Sample Size'
COLUMN column_analyzed  FORMAT A19 HEADING 'Last Analyzed'

PROMPT
PROMPT === Column statistics and histograms ===
PROMPT

SELECT
    column_name AS stats_column,
    num_distinct,
    num_nulls,
    density,
    num_buckets,
    histogram,
    sample_size AS column_sample,
    TO_CHAR(last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS column_analyzed
FROM dba_tab_col_statistics
WHERE owner = :object_owner
  AND table_name = :object_name
ORDER BY column_name;

COLUMN modification_partition FORMAT A28 HEADING 'Partition'
COLUMN inserts                FORMAT 999,999,999,999
COLUMN updates                FORMAT 999,999,999,999
COLUMN deletes                FORMAT 999,999,999,999
COLUMN modifications_at       FORMAT A19 HEADING 'Last Modified'
COLUMN truncated              FORMAT A9

PROMPT
PROMPT === Object modification statistics ===
PROMPT

-- Monitoring data can lag until DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO runs.
SELECT
    NVL(m.partition_name, '(table)') AS modification_partition,
    m.inserts,
    m.updates,
    m.deletes,
    TO_CHAR(m.timestamp, 'YYYY-MM-DD HH24:MI:SS') AS modifications_at,
    m.truncated
FROM dba_tab_modifications m
WHERE m.table_owner = :object_owner
  AND m.table_name = :object_name
ORDER BY m.partition_name NULLS FIRST;

COLUMN index_owner       FORMAT A18
COLUMN index_name        FORMAT A28
COLUMN index_type        FORMAT A16
COLUMN uniqueness        FORMAT A6  HEADING 'Unique'
COLUMN index_status      FORMAT A8  HEADING 'Status'
COLUMN visibility        FORMAT A7  HEADING 'Visible'
COLUMN index_columns     FORMAT A60 HEADING 'Columns (truncated)'
COLUMN distinct_keys     FORMAT 999,999,999,999
COLUMN leaf_blocks       FORMAT 999,999,999,999
COLUMN clustering_factor FORMAT 999,999,999,999
COLUMN index_size_mb     FORMAT 999,999,990.00
COLUMN index_analyzed    FORMAT A19

PROMPT
PROMPT === Index definitions ===
PROMPT

WITH index_columns AS (
    SELECT index_owner,
           index_name,
           LISTAGG(column_name, ', ') WITHIN GROUP (ORDER BY column_position)
               AS index_columns
    FROM dba_ind_columns
    WHERE table_owner = :object_owner
      AND table_name = :object_name
    GROUP BY index_owner, index_name
),
index_sizes AS (
    SELECT owner,
           segment_name AS index_name,
           SUM(bytes) AS bytes
    FROM dba_segments
    WHERE segment_type LIKE 'INDEX%'
    GROUP BY owner, segment_name
)
SELECT
    i.owner AS index_owner,
    i.index_name,
    i.index_type,
    i.uniqueness,
    i.status AS index_status,
    i.visibility,
    c.index_columns,
    ROUND(NVL(sz.bytes, 0) / 1024 / 1024, 2) AS index_size_mb
FROM dba_indexes i
LEFT JOIN index_columns c
  ON c.index_owner = i.owner
 AND c.index_name = i.index_name
LEFT JOIN index_sizes sz
  ON sz.owner = i.owner
 AND sz.index_name = i.index_name
WHERE i.table_owner = :object_owner
  AND i.table_name = :object_name
ORDER BY i.index_name;

PROMPT
PROMPT === Index statistics ===
PROMPT

SELECT
    i.index_name,
    i.distinct_keys,
    i.leaf_blocks,
    i.clustering_factor,
    TO_CHAR(i.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS index_analyzed
FROM dba_indexes i
WHERE i.table_owner = :object_owner
  AND i.table_name = :object_name
ORDER BY i.index_name;

COLUMN constraint_name    FORMAT A28
COLUMN constraint_type    FORMAT A12 HEADING 'Type'
COLUMN constraint_columns FORMAT A50 HEADING 'Columns (truncated)'
COLUMN constraint_status  FORMAT A8 HEADING 'Status'
COLUMN validated          FORMAT A10
COLUMN deferrable         FORMAT A10
COLUMN deferred           FORMAT A8
COLUMN fk_table           FORMAT A35 HEADING 'Foreign Key Table'
COLUMN fk_name            FORMAT A25 HEADING 'Foreign Key'
COLUMN fk_columns         FORMAT A38 HEADING 'FK Columns (truncated)'
COLUMN delete_rule        FORMAT A10
COLUMN referenced_table   FORMAT A35 HEADING 'Referenced Table'
COLUMN referenced_key     FORMAT A25 HEADING 'Referenced Key'

PROMPT
PROMPT === Constraints ===
PROMPT

WITH constraint_columns AS (
    SELECT owner,
           constraint_name,
           LISTAGG(column_name, ', ') WITHIN GROUP (ORDER BY position)
               AS constraint_columns
    FROM dba_cons_columns
    WHERE owner = :object_owner
      AND table_name = :object_name
    GROUP BY owner, constraint_name
)
SELECT
    c.constraint_name,
    CASE c.constraint_type
        WHEN 'P' THEN 'PRIMARY KEY'
        WHEN 'U' THEN 'UNIQUE'
        WHEN 'R' THEN 'FOREIGN KEY'
        WHEN 'C' THEN 'CHECK'
        ELSE c.constraint_type
    END AS constraint_type,
    cc.constraint_columns,
    c.status AS constraint_status,
    c.validated,
    c.deferrable,
    c.deferred
FROM dba_constraints c
LEFT JOIN constraint_columns cc
  ON cc.owner = c.owner
 AND cc.constraint_name = c.constraint_name
WHERE c.owner = :object_owner
  AND c.table_name = :object_name
ORDER BY
    CASE c.constraint_type
        WHEN 'P' THEN 1
        WHEN 'U' THEN 2
        WHEN 'R' THEN 3
        WHEN 'C' THEN 4
        ELSE 5
    END,
    c.constraint_name;

PROMPT
PROMPT === Foreign keys on this table ===
PROMPT

WITH fk_columns AS (
    SELECT owner,
           constraint_name,
           LISTAGG(column_name, ', ') WITHIN GROUP (ORDER BY position)
               AS fk_columns
    FROM dba_cons_columns
    WHERE owner = :object_owner
      AND table_name = :object_name
    GROUP BY owner, constraint_name
)
SELECT
    child.constraint_name AS fk_name,
    cols.fk_columns,
    parent.owner || '.' || parent.table_name AS referenced_table,
    parent.constraint_name AS referenced_key,
    child.delete_rule
FROM dba_constraints child
JOIN dba_constraints parent
  ON parent.owner = child.r_owner
 AND parent.constraint_name = child.r_constraint_name
LEFT JOIN fk_columns cols
  ON cols.owner = child.owner
 AND cols.constraint_name = child.constraint_name
WHERE child.owner = :object_owner
  AND child.table_name = :object_name
  AND child.constraint_type = 'R'
ORDER BY child.constraint_name;

PROMPT
PROMPT === Foreign keys referencing this table ===
PROMPT

WITH inbound_keys AS (
    SELECT
        child.owner,
        child.table_name,
        child.constraint_name,
        child.delete_rule,
        parent.constraint_name AS referenced_key
    FROM dba_constraints parent
    JOIN dba_constraints child
      ON child.r_owner = parent.owner
     AND child.r_constraint_name = parent.constraint_name
     AND child.constraint_type = 'R'
    WHERE parent.owner = :object_owner
      AND parent.table_name = :object_name
      AND parent.constraint_type IN ('P', 'U')
),
inbound_columns AS (
    SELECT
        fk.owner,
        fk.table_name,
        fk.constraint_name,
        fk.delete_rule,
        fk.referenced_key,
        LISTAGG(cc.column_name, ', ')
            WITHIN GROUP (ORDER BY cc.position) AS fk_columns
    FROM inbound_keys fk
    JOIN dba_cons_columns cc
      ON cc.owner = fk.owner
     AND cc.table_name = fk.table_name
     AND cc.constraint_name = fk.constraint_name
    GROUP BY
        fk.owner,
        fk.table_name,
        fk.constraint_name,
        fk.delete_rule,
        fk.referenced_key
)
SELECT
    owner || '.' || table_name AS fk_table,
    constraint_name AS fk_name,
    fk_columns,
    referenced_key,
    delete_rule
FROM inbound_columns
ORDER BY owner, table_name, constraint_name;

COLUMN trigger_name     FORMAT A28
COLUMN trigger_type     FORMAT A22
COLUMN triggering_event FORMAT A35 HEADING 'Triggering Event'
COLUMN trigger_status   FORMAT A8  HEADING 'Status'
COLUMN action_type      FORMAT A10 HEADING 'Action'
COLUMN when_clause      FORMAT A50 TRUNCATED HEADING 'When Clause (truncated)'

PROMPT
PROMPT === Triggers ===
PROMPT

SELECT
    trigger_name,
    trigger_type,
    triggering_event,
    status AS trigger_status,
    action_type,
    when_clause
FROM dba_triggers
WHERE table_owner = :object_owner
  AND table_name = :object_name
ORDER BY trigger_name;

COLUMN dependent_owner FORMAT A18 HEADING 'Owner'
COLUMN dependent_name  FORMAT A35 HEADING 'View / MView'
COLUMN dependent_type  FORMAT A18 HEADING 'Object Type'
COLUMN object_status   FORMAT A8  HEADING 'Status'
COLUMN dependency_type FORMAT A14 HEADING 'Dependency'

PROMPT
PROMPT === Referencing views and materialized views ===
PROMPT

-- DBA_DEPENDENCIES records direct dependencies resolved by Oracle.
SELECT DISTINCT
    d.owner AS dependent_owner,
    d.name AS dependent_name,
    d.type AS dependent_type,
    o.status AS object_status,
    d.dependency_type
FROM dba_dependencies d
LEFT JOIN dba_objects o
  ON o.owner = d.owner
 AND o.object_name = d.name
 AND o.object_type = d.type
WHERE d.referenced_owner = :object_owner
  AND d.referenced_name = :object_name
  AND d.referenced_type = 'TABLE'
  AND d.type IN ('VIEW', 'MATERIALIZED VIEW')
ORDER BY d.owner, d.type, d.name;

SET FEEDBACK ON
