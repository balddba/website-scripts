/*******************************************************************************
*
* Script Name: partitions.sql
* Title: Partition metadata and statistics
* Tags: Partitions, Statistics
* Purpose: Report partition keys, bounds, tablespace, and statistics for a table or index
*
* Description:
*   Reads DBA_PART_KEY_COLUMNS for the partition key, then partition rows from
*   DBA_TAB_PARTITIONS or DBA_IND_PARTITIONS. HIGH_VALUE is a LONG bound
*   expression; SET LONG controls how much of it is printed. Table partitions
*   show row and block counts. Index partitions include STATUS (USABLE or
*   UNUSABLE). Object type defaults to TABLE.
*
* Parameters:
*   &1 - Owner. Default: current USER
*   &2 - Table or index name (required)
*   &3 - (Optional) Object type: TABLE or INDEX. Default: TABLE
*
* Required Privileges:
*   - SELECT on DBA_PART_KEY_COLUMNS
*   - SELECT on DBA_PART_TABLES
*   - SELECT on DBA_PART_INDEXES
*   - SELECT on DBA_TAB_PARTITIONS
*   - SELECT on DBA_IND_PARTITIONS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Partitioning method and key columns
*   - One row per partition: position, high value, tablespace, stats, status
*
* Example Usage:
*   SQL> @partitions.sql SH SALES
*   SQL> @partitions.sql SH SALES TABLE
*   SQL> @partitions.sql SH SALES_PK INDEX
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 240
SET PAGESIZE 100
SET LONG 4000
SET LONGCHUNKSIZE 4000
SET TRIMSPOOL ON
SET TAB OFF
SET WRAP OFF

-- Optional &1/&3: SQL*Plus prompts if omitted; Enter uses USER and TABLE.
COLUMN c_owner NEW_VALUE p_owner NOPRINT
COLUMN c_name  NEW_VALUE p_name  NOPRINT
COLUMN c_type  NEW_VALUE p_type  NOPRINT
SELECT
    NVL(CAST(TRIM('&1') AS VARCHAR2(128)), USER) AS c_owner,
    NULLIF(TRIM('&2'), '') AS c_name,
    NVL(CAST(UPPER(TRIM('&3')) AS VARCHAR2(128)), 'TABLE') AS c_type
FROM dual;

VARIABLE object_owner VARCHAR2(128)
VARIABLE object_name  VARCHAR2(128)
VARIABLE object_type  VARCHAR2(5)

DECLARE
    l_owner        VARCHAR2(128) := UPPER(TRIM('&&p_owner'));
    l_object_name  VARCHAR2(128) := UPPER(TRIM('&&p_name'));
    l_object_type  VARCHAR2(10)  := UPPER(TRIM('&&p_type'));
    l_count        PLS_INTEGER;
BEGIN
    IF l_object_name IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'Table or index name is required.');
    END IF;

    IF l_object_type IN ('TAB', 'T') THEN
        l_object_type := 'TABLE';
    ELSIF l_object_type IN ('IND', 'I', 'IDX') THEN
        l_object_type := 'INDEX';
    END IF;

    IF l_object_type NOT IN ('TABLE', 'INDEX') THEN
        RAISE_APPLICATION_ERROR(-20002, 'Object type must be TABLE or INDEX.');
    END IF;

    IF NOT REGEXP_LIKE(l_owner, '^[A-Z][A-Z0-9_$#]*$')
       OR NOT REGEXP_LIKE(l_object_name, '^[A-Z][A-Z0-9_$#]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'Owner and name must be ordinary Oracle identifiers.'
        );
    END IF;

    IF l_object_type = 'TABLE' THEN
        SELECT COUNT(*)
        INTO l_count
        FROM dba_part_tables
        WHERE owner = l_owner
          AND table_name = l_object_name;
    ELSE
        SELECT COUNT(*)
        INTO l_count
        FROM dba_part_indexes
        WHERE owner = l_owner
          AND index_name = l_object_name;
    END IF;

    IF l_count = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20004,
            l_object_type || ' ' || l_owner || '.' || l_object_name
            || ' was not found or is not partitioned.'
        );
    END IF;

    :object_owner := l_owner;
    :object_name  := l_object_name;
    :object_type  := l_object_type;
END;
/

COLUMN owner              FORMAT A16  HEADING 'Owner'
COLUMN object_name        FORMAT A30  HEADING 'Name'
COLUMN object_type        FORMAT A6   HEADING 'Type'
COLUMN partitioning_type  FORMAT A12  HEADING 'Method'
COLUMN subpartitioning_type FORMAT A12 HEADING 'Submethod'
COLUMN partition_count    FORMAT 999,990 HEADING 'Parts'
COLUMN locality           FORMAT A8   HEADING 'Locality'
COLUMN alignment          FORMAT A10  HEADING 'Alignment'
COLUMN interval_clause    FORMAT A40 TRUNC HEADING 'Interval'
COLUMN column_position    FORMAT 990  HEADING 'Pos'
COLUMN column_name        FORMAT A30  HEADING 'Key Column'
COLUMN partition_position FORMAT 9990 HEADING 'Pos'
COLUMN partition_name     FORMAT A30  HEADING 'Partition'
COLUMN tablespace_name    FORMAT A22  HEADING 'Tablespace'
COLUMN high_value         FORMAT A48  HEADING 'High Value'
COLUMN num_rows           FORMAT 999,999,999,990 HEADING 'Rows'
COLUMN blocks             FORMAT 999,999,990 HEADING 'Blocks'
COLUMN leaf_blocks        FORMAT 999,999,990 HEADING 'Leaf Blks'
COLUMN status             FORMAT A10  HEADING 'Status'
COLUMN last_analyzed      FORMAT A19  HEADING 'Last Analyzed'

PROMPT
PROMPT === Partition method ===
PROMPT

SELECT
    pt.owner,
    pt.table_name AS object_name,
    'TABLE' AS object_type,
    pt.partitioning_type,
    pt.subpartitioning_type,
    pt.partition_count,
    CAST(NULL AS VARCHAR2(8)) AS locality,
    CAST(NULL AS VARCHAR2(10)) AS alignment,
    pt.interval AS interval_clause
FROM dba_part_tables pt
WHERE pt.owner = :object_owner
  AND pt.table_name = :object_name
  AND :object_type = 'TABLE'
UNION ALL
SELECT
    pi.owner,
    pi.index_name AS object_name,
    'INDEX' AS object_type,
    pi.partitioning_type,
    pi.subpartitioning_type,
    pi.partition_count,
    pi.locality,
    pi.alignment,
    pi.interval AS interval_clause
FROM dba_part_indexes pi
WHERE pi.owner = :object_owner
  AND pi.index_name = :object_name
  AND :object_type = 'INDEX';

PROMPT
PROMPT === Partition key columns ===
PROMPT

SELECT
    owner,
    name AS object_name,
    object_type,
    column_position,
    column_name
FROM dba_part_key_columns
WHERE owner = :object_owner
  AND name = :object_name
  AND object_type = :object_type
ORDER BY column_position;

PROMPT
PROMPT === Table partition statistics ===
PROMPT Empty when the object type is INDEX. HIGH_VALUE is a LONG expression.
PROMPT

SELECT
    p.table_owner AS owner,
    p.table_name AS object_name,
    'TABLE' AS object_type,
    p.partition_position,
    p.partition_name,
    p.tablespace_name,
    p.high_value,
    p.num_rows,
    p.blocks,
    CASE p.segment_created
        WHEN 'YES' THEN 'CREATED'
        WHEN 'NO'  THEN 'NONE'
        ELSE NVL(p.segment_created, 'N/A')
    END AS status,
    TO_CHAR(p.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS last_analyzed
FROM dba_tab_partitions p
WHERE p.table_owner = :object_owner
  AND p.table_name = :object_name
  AND :object_type = 'TABLE'
ORDER BY p.partition_position;

PROMPT
PROMPT === Index partition statistics ===
PROMPT Empty when the object type is TABLE. STATUS is USABLE or UNUSABLE.
PROMPT

SELECT
    ip.index_owner AS owner,
    ip.index_name AS object_name,
    'INDEX' AS object_type,
    ip.partition_position,
    ip.partition_name,
    ip.tablespace_name,
    ip.high_value,
    ip.num_rows,
    ip.leaf_blocks,
    ip.status,
    TO_CHAR(ip.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS last_analyzed
FROM dba_ind_partitions ip
WHERE ip.index_owner = :object_owner
  AND ip.index_name = :object_name
  AND :object_type = 'INDEX'
ORDER BY ip.partition_position;

UNDEFINE p_owner
UNDEFINE p_name
UNDEFINE p_type
UNDEFINE 1
UNDEFINE 2
UNDEFINE 3

SET FEEDBACK ON
SET VERIFY ON
