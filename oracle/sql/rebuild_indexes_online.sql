/*******************************************************************************
*
* Script Name: rebuild_indexes_online.sql
* Title: Rebuild indexes online into a tablespace
* Tags: Indexes, Maintenance, Tablespaces
* Purpose: Rebuild indexes online into a target tablespace and show before/after tablespace and statistics
*
* Description:
*   Issues ALTER INDEX ... REBUILD ONLINE TABLESPACE <target> for every
*   rebuildable index on a table, or for one named index. The object name is
*   resolved as a table first, then as an index in the same schema. Bitmap,
*   IOT, LOB, cluster, and domain indexes are skipped. Partitioned indexes
*   are rebuilt partition by partition (or subpartition when composite).
*   Each statement is printed; a failure does not stop the remaining rebuilds.
*
* Parameters:
*   &1 - Owner. Default: current USER
*   &2 - Table name or index name (required)
*   &3 - Target tablespace (required)
*
* Required Privileges:
*   - SELECT on DBA_TABLES
*   - SELECT on DBA_INDEXES
*   - SELECT on DBA_IND_PARTITIONS
*   - SELECT on DBA_IND_SUBPARTITIONS
*   - SELECT on DBA_TABLESPACES
*   - ALTER privilege on each selected index (or ALTER ANY INDEX)
*
* Output Format:
*   - Index tablespace and statistics before the rebuild
*   - Each ALTER INDEX statement with OK or the Oracle error
*   - Index tablespace and statistics after the rebuild
*   - Attempted, succeeded, failed, and skipped counts
*
* Example Usage:
*   SQL> @rebuild_indexes_online.sql HR EMPLOYEES INDX
*   SQL> @rebuild_indexes_online.sql HR EMP_EMP_ID_PK INDX
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

-- Optional &1: SQL*Plus prompts if omitted; Enter uses current USER.
COLUMN c_owner NEW_VALUE p_owner NOPRINT
COLUMN c_object NEW_VALUE p_object NOPRINT
COLUMN c_ts NEW_VALUE p_ts NOPRINT
SELECT
    NVL(CAST(TRIM('&1') AS VARCHAR2(128)), USER) AS c_owner,
    NULLIF(TRIM('&2'), '') AS c_object,
    NULLIF(TRIM('&3'), '') AS c_ts
FROM dual;

VARIABLE object_owner VARCHAR2(128)
VARIABLE table_name   VARCHAR2(128)
VARIABLE index_name   VARCHAR2(128)
VARIABLE target_ts    VARCHAR2(128)

DECLARE
    l_owner        VARCHAR2(128) := UPPER(TRIM('&&p_owner'));
    l_object_name  VARCHAR2(128) := UPPER(TRIM('&&p_object'));
    l_tablespace   VARCHAR2(128) := UPPER(TRIM('&&p_ts'));
    l_table_count  PLS_INTEGER;
    l_index_count  PLS_INTEGER;
    l_ts_count     PLS_INTEGER;
    l_ts_contents  VARCHAR2(30);
    l_ts_status    VARCHAR2(9);
BEGIN
    IF l_object_name IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'Table name or index name is required.');
    END IF;

    IF l_tablespace IS NULL THEN
        RAISE_APPLICATION_ERROR(-20002, 'Target tablespace is required.');
    END IF;

    IF NOT REGEXP_LIKE(l_owner, '^[A-Z][A-Z0-9_$#]*$')
       OR NOT REGEXP_LIKE(l_object_name, '^[A-Z][A-Z0-9_$#]*$')
       OR NOT REGEXP_LIKE(l_tablespace, '^[A-Z][A-Z0-9_$#]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'Owner, object, and tablespace must be ordinary Oracle identifiers.'
        );
    END IF;

    SELECT COUNT(*), MAX(contents), MAX(status)
    INTO l_ts_count, l_ts_contents, l_ts_status
    FROM dba_tablespaces
    WHERE tablespace_name = l_tablespace;

    IF l_ts_count = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20004,
            'Tablespace ' || l_tablespace || ' was not found.'
        );
    END IF;

    IF l_ts_contents <> 'PERMANENT' THEN
        RAISE_APPLICATION_ERROR(
            -20005,
            'Target tablespace must be PERMANENT, not ' || l_ts_contents || '.'
        );
    END IF;

    IF l_ts_status <> 'ONLINE' THEN
        RAISE_APPLICATION_ERROR(
            -20006,
            'Target tablespace ' || l_tablespace || ' is ' || l_ts_status || '.'
        );
    END IF;

    SELECT COUNT(*)
    INTO l_table_count
    FROM dba_tables
    WHERE owner = l_owner
      AND table_name = l_object_name;

    SELECT COUNT(*)
    INTO l_index_count
    FROM dba_indexes
    WHERE owner = l_owner
      AND index_name = l_object_name;

    IF l_table_count > 0 THEN
        :object_owner := l_owner;
        :table_name   := l_object_name;
        :index_name   := '%';
    ELSIF l_index_count > 0 THEN
        :object_owner := l_owner;
        :index_name   := l_object_name;
        SELECT table_name
        INTO :table_name
        FROM dba_indexes
        WHERE owner = l_owner
          AND index_name = l_object_name
          AND ROWNUM = 1;
    ELSE
        RAISE_APPLICATION_ERROR(
            -20007,
            'No table or index named ' || l_owner || '.' || l_object_name || ' was found.'
        );
    END IF;

    :target_ts := l_tablespace;
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
PROMPT === Index tablespace and statistics before rebuild ===
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
WHERE i.table_name = :table_name
  AND (
        (:index_name = '%' AND i.table_owner = :object_owner)
        OR
        (:index_name <> '%' AND i.owner = :object_owner AND i.index_name = :index_name)
      )
ORDER BY i.index_name;

PROMPT
PROMPT === Rebuild ONLINE TABLESPACE ===
PROMPT

DECLARE
    l_owner      VARCHAR2(128) := :object_owner;
    l_table_name VARCHAR2(128) := :table_name;
    l_index_name VARCHAR2(128) := :index_name;
    l_tablespace VARCHAR2(128) := :target_ts;
    l_sql        VARCHAR2(1000);
    l_attempted  PLS_INTEGER := 0;
    l_succeeded  PLS_INTEGER := 0;
    l_failed     PLS_INTEGER := 0;
    l_skipped    PLS_INTEGER := 0;

    FUNCTION quote_name(p_name IN VARCHAR2) RETURN VARCHAR2 IS
    BEGIN
        RETURN '"' || REPLACE(p_name, '"', '""') || '"';
    END quote_name;

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
        'Rebuild ONLINE TABLESPACE ' || l_tablespace
        || ' for ' || l_owner || '.' || l_table_name
        || ' (index: ' || l_index_name || ')'
    );
    DBMS_OUTPUT.PUT_LINE(RPAD('-', 78, '-'));

    FOR idx IN (
        SELECT owner,
               index_name,
               index_type,
               partitioned
        FROM dba_indexes
        WHERE table_name = l_table_name
          AND (
                (l_index_name = '%' AND table_owner = l_owner)
                OR
                (l_index_name <> '%' AND owner = l_owner AND index_name = l_index_name)
              )
        ORDER BY index_name
    ) LOOP
        IF idx.index_type NOT IN (
            'NORMAL',
            'NORMAL/REV',
            'FUNCTION-BASED NORMAL'
        ) THEN
            l_skipped := l_skipped + 1;
            DBMS_OUTPUT.PUT_LINE(
                'SKIP  ' || idx.owner || '.' || idx.index_name
                || ' (type ' || idx.index_type
                || '; ONLINE tablespace rebuild supports B-tree indexes only)'
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
                              || quote_name(sub.subpartition_name)
                              || ' ONLINE TABLESPACE '
                              || quote_name(l_tablespace);
                        rebuild_one(l_sql);
                    END LOOP;
                ELSE
                    l_sql := 'ALTER INDEX ' || quote_name(idx.owner) || '.'
                          || quote_name(idx.index_name)
                          || ' REBUILD PARTITION '
                          || quote_name(part.partition_name)
                          || ' ONLINE TABLESPACE '
                          || quote_name(l_tablespace);
                    rebuild_one(l_sql);
                END IF;
            END LOOP;
        ELSE
            l_sql := 'ALTER INDEX ' || quote_name(idx.owner) || '.'
                  || quote_name(idx.index_name)
                  || ' REBUILD ONLINE TABLESPACE '
                  || quote_name(l_tablespace);
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
PROMPT === Index tablespace and statistics after rebuild ===
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
WHERE i.table_name = :table_name
  AND (
        (:index_name = '%' AND i.table_owner = :object_owner)
        OR
        (:index_name <> '%' AND i.owner = :object_owner AND i.index_name = :index_name)
      )
ORDER BY i.index_name;

UNDEFINE p_owner
UNDEFINE p_object
UNDEFINE p_ts
UNDEFINE 1
UNDEFINE 2
UNDEFINE 3

SET FEEDBACK ON
SET VERIFY ON
