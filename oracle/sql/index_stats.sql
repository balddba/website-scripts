/*******************************************************************************
*
* Script Name: index_stats.sql
* Title: Index statistics
* Tags: Indexes, Statistics
* Purpose: Report DBA_INDEXES statistics for every index on a table, or one index
*
* Description:
*   Lists B-tree and related index statistics from DBA_INDEXES: leaf blocks,
*   height (BLEVEL), distinct keys, average leaf and data blocks per key,
*   clustering factor, row count, uniqueness, tablespace, last analyzed,
*   partitioned flag, and status. Supply a table name, an index name, or both.
*   Press Enter at optional prompts to use the defaults.
*
* Parameters:
*   &1 - Owner. Default: current USER
*   &2 - (Optional) Table name. Default: all tables for the chosen index
*   &3 - (Optional) Index name. Default: all indexes on the table
*        At least one of table name or index name is required.
*
* Required Privileges:
*   - SELECT on DBA_INDEXES
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - One row per matching index with storage, uniqueness, and optimizer stats
*
* Example Usage:
*   SQL> @index_stats.sql HR EMPLOYEES
*   SQL> @index_stats.sql HR EMPLOYEES EMP_EMP_ID_PK
*   SQL> @index_stats.sql HR % EMP_EMP_ID_PK
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 240
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF
SET WRAP OFF

-- Optional &1/&2/&3: SQL*Plus prompts if omitted; Enter uses USER / % / %.
COLUMN c_owner NEW_VALUE p_owner NOPRINT
COLUMN c_table NEW_VALUE p_table NOPRINT
COLUMN c_index NEW_VALUE p_index NOPRINT
SELECT
    NVL(CAST(TRIM('&1') AS VARCHAR2(128)), USER) AS c_owner,
    NVL(CAST(TRIM('&2') AS VARCHAR2(128)), '%') AS c_table,
    NVL(CAST(TRIM('&3') AS VARCHAR2(128)), '%') AS c_index
FROM dual;

VARIABLE object_owner VARCHAR2(128)
VARIABLE table_name   VARCHAR2(128)
VARIABLE index_name   VARCHAR2(128)

DECLARE
    l_owner       VARCHAR2(128) := UPPER(TRIM('&&p_owner'));
    l_table_name  VARCHAR2(128) := UPPER(TRIM('&&p_table'));
    l_index_name  VARCHAR2(128) := UPPER(TRIM('&&p_index'));
    l_index_count PLS_INTEGER;
BEGIN
    IF l_table_name = '%' AND l_index_name = '%' THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Provide a table name, an index name, or both.'
        );
    END IF;

    IF NOT REGEXP_LIKE(l_owner, '^[A-Z][A-Z0-9_$#]*$')
       OR (l_table_name <> '%'
           AND NOT REGEXP_LIKE(l_table_name, '^[A-Z][A-Z0-9_$#]*$'))
       OR (l_index_name <> '%'
           AND NOT REGEXP_LIKE(l_index_name, '^[A-Z][A-Z0-9_$#]*$')) THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Owner, table, and index must be ordinary Oracle identifiers; only % is supported as a wildcard.'
        );
    END IF;

    SELECT COUNT(*)
    INTO l_index_count
    FROM dba_indexes
    WHERE (
            (l_table_name <> '%'
             AND table_owner = l_owner
             AND table_name = l_table_name)
            OR
            (l_table_name = '%'
             AND owner = l_owner
             AND index_name = l_index_name)
          )
      AND (l_index_name = '%' OR index_name = l_index_name);

    IF l_index_count = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'No indexes found for owner=' || l_owner
            || ' table=' || l_table_name
            || ' index=' || l_index_name || '.'
        );
    END IF;

    :object_owner := l_owner;
    :table_name   := l_table_name;
    :index_name   := l_index_name;
END;
/

COLUMN owner                   FORMAT A16               HEADING 'Owner'
COLUMN table_name              FORMAT A28               HEADING 'Table'
COLUMN index_name              FORMAT A30               HEADING 'Index'
COLUMN uniqueness              FORMAT A10               HEADING 'Unique'
COLUMN status                  FORMAT A10               HEADING 'Status'
COLUMN partitioned             FORMAT A4                HEADING 'Part'
COLUMN tablespace_name         FORMAT A20               HEADING 'Tablespace'
COLUMN blevel                  FORMAT 9990              HEADING 'Blevel'
COLUMN leaf_blocks             FORMAT 999,999,990       HEADING 'Leaf Blks'
COLUMN distinct_keys           FORMAT 999,999,999,990   HEADING 'Distinct'
COLUMN avg_leaf_blocks_per_key FORMAT 999,990.00        HEADING 'Avg Leaf/Key'
COLUMN avg_data_blocks_per_key FORMAT 999,990.00        HEADING 'Avg Data/Key'
COLUMN clustering_factor       FORMAT 999,999,999,990   HEADING 'Clust Factor'
COLUMN num_rows                FORMAT 999,999,999,990   HEADING 'Rows'
COLUMN last_analyzed           FORMAT A19               HEADING 'Last Analyzed'

PROMPT
PROMPT === Index statistics ===
PROMPT

SELECT
    i.owner,
    i.table_name,
    i.index_name,
    i.uniqueness,
    i.status,
    i.partitioned,
    i.tablespace_name,
    i.blevel,
    i.leaf_blocks,
    i.distinct_keys,
    i.avg_leaf_blocks_per_key,
    i.avg_data_blocks_per_key,
    i.clustering_factor,
    i.num_rows,
    TO_CHAR(i.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS last_analyzed
FROM dba_indexes i
WHERE (
        (:table_name <> '%'
         AND i.table_owner = :object_owner
         AND i.table_name = :table_name)
        OR
        (:table_name = '%'
         AND i.owner = :object_owner
         AND i.index_name = :index_name)
      )
  AND (:index_name = '%' OR i.index_name = :index_name)
ORDER BY i.table_name, i.index_name;

UNDEFINE p_owner
UNDEFINE p_table
UNDEFINE p_index
UNDEFINE 1
UNDEFINE 2
UNDEFINE 3

SET FEEDBACK ON
SET VERIFY ON
