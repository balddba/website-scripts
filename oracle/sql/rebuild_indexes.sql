/*******************************************************************************
*
* Script Name: rebuild_indexes.sql
* Title: Rebuild indexes
* Tags: Indexes, Maintenance
* Purpose: Print index statistics, rebuild one index or every index on a table, then print statistics again
*
* Description:
*   Shows current DBA_INDEXES statistics, issues ALTER INDEX ... REBUILD for
*   each matching B-tree or bitmap index, then shows statistics again so you
*   can compare leaf blocks, height, and clustering factor. Partitioned
*   indexes are rebuilt partition by partition (or subpartition when
*   composite). IOT, LOB, cluster, and domain indexes are skipped. ONLINE
*   is optional and is not applied to bitmap indexes. Each statement is
*   printed; a failure does not stop the remaining rebuilds.
*
* Parameters:
*   &1 - Owner. Default: current USER
*   &2 - Table name (required)
*   &3 - (Optional) Index name. Default: all rebuildable indexes on the table
*   &4 - (Optional) ONLINE: YES or NO. Default: NO
*
* Required Privileges:
*   - SELECT on DBA_TABLES
*   - SELECT on DBA_INDEXES
*   - SELECT on DBA_IND_PARTITIONS
*   - SELECT on DBA_IND_SUBPARTITIONS
*   - ALTER privilege on each selected index (or ALTER ANY INDEX)
*
* Output Format:
*   - Index statistics before the rebuild
*   - Each ALTER INDEX statement with OK or the Oracle error
*   - Index statistics after the rebuild
*   - Attempted, succeeded, failed, and skipped counts
*
* Example Usage:
*   SQL> @rebuild_indexes.sql HR EMPLOYEES
*   SQL> @rebuild_indexes.sql HR EMPLOYEES EMP_NAME_IX
*   SQL> @rebuild_indexes.sql HR EMPLOYEES % YES
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET SERVEROUTPUT ON SIZE UNLIMITED
SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 240
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF
SET WRAP OFF

-- Optional &1/&3/&4: SQL*Plus prompts if omitted; Enter uses USER / all indexes / NO.
COLUMN c_owner  NEW_VALUE p_owner  NOPRINT
COLUMN c_table  NEW_VALUE p_table  NOPRINT
COLUMN c_index  NEW_VALUE p_index  NOPRINT
COLUMN c_online NEW_VALUE p_online NOPRINT
SELECT
    NVL(CAST(TRIM('&1') AS VARCHAR2(128)), USER) AS c_owner,
    CAST(TRIM('&2') AS VARCHAR2(128)) AS c_table,
    NVL(CAST(TRIM('&3') AS VARCHAR2(128)), '%') AS c_index,
    NVL(CAST(UPPER(TRIM('&4')) AS VARCHAR2(128)), 'NO') AS c_online
FROM dual;

VARIABLE object_owner VARCHAR2(128)
VARIABLE table_name   VARCHAR2(128)
VARIABLE index_name   VARCHAR2(128)
VARIABLE online_flag  VARCHAR2(3)

DECLARE
    l_owner       VARCHAR2(128) := UPPER(TRIM('&&p_owner'));
    l_table_name  VARCHAR2(128) := UPPER(TRIM('&&p_table'));
    l_index_name  VARCHAR2(128) := UPPER(TRIM('&&p_index'));
    l_online      VARCHAR2(8)   := UPPER(TRIM('&&p_online'));
    l_table_count PLS_INTEGER;
BEGIN
    IF l_table_name IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'Table name is required.');
    END IF;

    IF l_online IN ('Y', 'TRUE', 'ONLINE') THEN
        l_online := 'YES';
    ELSIF l_online IN ('N', 'FALSE', 'OFFLINE') THEN
        l_online := 'NO';
    END IF;

    IF l_online NOT IN ('YES', 'NO') THEN
        RAISE_APPLICATION_ERROR(-20002, 'ONLINE must be YES or NO.');
    END IF;

    IF NOT REGEXP_LIKE(l_owner, '^[A-Z][A-Z0-9_$#]*$')
       OR NOT REGEXP_LIKE(l_table_name, '^[A-Z][A-Z0-9_$#]*$')
       OR (l_index_name <> '%'
           AND NOT REGEXP_LIKE(l_index_name, '^[A-Z][A-Z0-9_$#]*$')) THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'Owner, table, and index must be ordinary Oracle identifiers; only % is supported as a wildcard.'
        );
    END IF;

    SELECT COUNT(*)
    INTO l_table_count
    FROM dba_tables
    WHERE owner = l_owner
      AND table_name = l_table_name;

    IF l_table_count = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20004,
            'Table ' || l_owner || '.' || l_table_name || ' was not found.'
        );
    END IF;

    :object_owner := l_owner;
    :table_name   := l_table_name;
    :index_name   := l_index_name;
    :online_flag  := l_online;
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
PROMPT === Index statistics before rebuild ===
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
WHERE i.table_owner = :object_owner
  AND i.table_name = :table_name
  AND (:index_name = '%' OR i.index_name = :index_name)
ORDER BY i.index_name;

PROMPT
PROMPT === Rebuild ===
PROMPT

DECLARE
    l_owner      VARCHAR2(128) := :object_owner;
    l_table_name VARCHAR2(128) := :table_name;
    l_index_name VARCHAR2(128) := :index_name;
    l_online     VARCHAR2(3)   := :online_flag;
    l_sql        VARCHAR2(1000);
    l_attempted  PLS_INTEGER := 0;
    l_succeeded  PLS_INTEGER := 0;
    l_failed     PLS_INTEGER := 0;
    l_skipped    PLS_INTEGER := 0;

    FUNCTION quote_name(p_name IN VARCHAR2) RETURN VARCHAR2 IS
    BEGIN
        RETURN '"' || REPLACE(p_name, '"', '""') || '"';
    END quote_name;

    FUNCTION is_bitmap(p_type IN VARCHAR2) RETURN BOOLEAN IS
    BEGIN
        RETURN p_type LIKE '%BITMAP%';
    END is_bitmap;

    PROCEDURE rebuild_one(p_sql IN VARCHAR2) IS
    BEGIN
        l_attempted := l_attempted + 1;
        DBMS_OUTPUT.PUT_LINE(p_sql || ';');
        BEGIN
            EXECUTE IMMEDIATE p_sql;
            l_succeeded := l_succeeded + 1;
            DBMS_OUTPUT.PUT_LINE('  OK');
        EXCEPTION
            WHEN OTHERS THEN
                l_failed := l_failed + 1;
                DBMS_OUTPUT.PUT_LINE('  ERROR ' || SQLCODE || ': ' || SQLERRM);
        END;
    END rebuild_one;
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Rebuild indexes on ' || l_owner || '.' || l_table_name
        || ' (index: ' || l_index_name || ', ONLINE: ' || l_online || ')'
    );
    DBMS_OUTPUT.PUT_LINE(RPAD('-', 78, '-'));

    FOR idx IN (
        SELECT owner,
               index_name,
               index_type,
               partitioned,
               uniqueness,
               status
        FROM dba_indexes
        WHERE table_owner = l_owner
          AND table_name = l_table_name
          AND (l_index_name = '%' OR index_name = l_index_name)
        ORDER BY index_name
    ) LOOP
        IF idx.index_type NOT IN (
            'NORMAL',
            'NORMAL/REV',
            'FUNCTION-BASED NORMAL',
            'BITMAP',
            'FUNCTION-BASED BITMAP'
        ) THEN
            l_skipped := l_skipped + 1;
            DBMS_OUTPUT.PUT_LINE(
                'SKIP  ' || idx.owner || '.' || idx.index_name
                || ' (type ' || idx.index_type || ')'
            );
            CONTINUE;
        END IF;

        IF l_online = 'YES' AND is_bitmap(idx.index_type) THEN
            l_skipped := l_skipped + 1;
            DBMS_OUTPUT.PUT_LINE(
                'SKIP  ' || idx.owner || '.' || idx.index_name
                || ' (bitmap indexes cannot be rebuilt ONLINE)'
            );
            CONTINUE;
        END IF;

        IF idx.partitioned = 'YES' THEN
            FOR part IN (
                SELECT partition_name,
                       composite
                FROM dba_ind_partitions
                WHERE index_owner = idx.owner
                  AND index_name = idx.index_name
                ORDER BY partition_position
            ) LOOP
                IF part.composite = 'YES' THEN
                    FOR sub IN (
                        SELECT subpartition_name
                        FROM dba_ind_subpartitions
                        WHERE index_owner = idx.owner
                          AND index_name = idx.index_name
                          AND partition_name = part.partition_name
                        ORDER BY subpartition_position
                    ) LOOP
                        l_sql := 'ALTER INDEX ' || quote_name(idx.owner) || '.'
                              || quote_name(idx.index_name)
                              || ' REBUILD SUBPARTITION '
                              || quote_name(sub.subpartition_name);
                        IF l_online = 'YES' THEN
                            l_sql := l_sql || ' ONLINE';
                        END IF;
                        rebuild_one(l_sql);
                    END LOOP;
                ELSE
                    l_sql := 'ALTER INDEX ' || quote_name(idx.owner) || '.'
                          || quote_name(idx.index_name)
                          || ' REBUILD PARTITION '
                          || quote_name(part.partition_name);
                    IF l_online = 'YES' THEN
                        l_sql := l_sql || ' ONLINE';
                    END IF;
                    rebuild_one(l_sql);
                END IF;
            END LOOP;
        ELSE
            l_sql := 'ALTER INDEX ' || quote_name(idx.owner) || '.'
                  || quote_name(idx.index_name) || ' REBUILD';
            IF l_online = 'YES' THEN
                l_sql := l_sql || ' ONLINE';
            END IF;
            rebuild_one(l_sql);
        END IF;
    END LOOP;

    DBMS_OUTPUT.PUT_LINE(RPAD('-', 78, '-'));
    DBMS_OUTPUT.PUT_LINE('Attempted: ' || l_attempted);
    DBMS_OUTPUT.PUT_LINE('Succeeded: ' || l_succeeded);
    DBMS_OUTPUT.PUT_LINE('Failed:    ' || l_failed);
    DBMS_OUTPUT.PUT_LINE('Skipped:   ' || l_skipped);

    IF l_attempted = 0 AND l_skipped = 0 THEN
        DBMS_OUTPUT.PUT_LINE('No matching indexes found.');
    END IF;
END;
/

PROMPT
PROMPT === Index statistics after rebuild ===
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
WHERE i.table_owner = :object_owner
  AND i.table_name = :table_name
  AND (:index_name = '%' OR i.index_name = :index_name)
ORDER BY i.index_name;

UNDEFINE p_owner
UNDEFINE p_table
UNDEFINE p_index
UNDEFINE p_online
UNDEFINE 1
UNDEFINE 2
UNDEFINE 3
UNDEFINE 4

SET FEEDBACK ON
SET VERIFY ON
