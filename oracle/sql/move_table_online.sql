/*******************************************************************************
*
* Script Name: move_table_online.sql
* Title: Move a table online
* Tags: Tables, Maintenance, Tablespaces
* Purpose: ALTER TABLE ... MOVE ONLINE TABLESPACE <target> and show before/after tablespace and table statistics
*
* Description:
*   Moves a heap table into a target tablespace with 12cR2+ MOVE ONLINE so
*   DML can continue. Partitioned tables are moved partition by partition
*   (or subpartition when composite). IOT, cluster, temporary, and nested
*   tables are rejected. Indexes should stay usable with ONLINE; confirm
*   STATUS after the move and rebuild with rebuild_indexes.sql if any are
*   UNUSABLE. MOVE does not gather fresh optimizer statistics.
*
* Parameters:
*   &1 - Owner. Default: current USER
*   &2 - Table name (required)
*   &3 - Target tablespace (required)
*
* Required Privileges:
*   - SELECT on DBA_TABLES
*   - SELECT on DBA_TAB_PARTITIONS
*   - SELECT on DBA_TAB_SUBPARTITIONS
*   - SELECT on DBA_INDEXES
*   - SELECT on DBA_TABLESPACES
*   - ALTER privilege on the table (or ALTER ANY TABLE)
*
* Output Format:
*   - Table tablespace and statistics before the move
*   - Index status before the move
*   - Each ALTER TABLE statement with OK or the Oracle error
*   - Table tablespace and statistics after the move
*   - Index status after the move
*
* Example Usage:
*   SQL> @move_table_online.sql HR EMPLOYEES USERS
*   SQL> @move_table_online.sql SH SALES DATA_HOT
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET SERVEROUTPUT ON SIZE UNLIMITED
SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 220
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF
SET WRAP OFF

-- Optional &1: SQL*Plus prompts if omitted; Enter uses current USER.
COLUMN c_owner NEW_VALUE p_owner NOPRINT
COLUMN c_table NEW_VALUE p_table NOPRINT
COLUMN c_ts NEW_VALUE p_ts NOPRINT
SELECT
    NVL(CAST(TRIM('&1') AS VARCHAR2(128)), USER) AS c_owner,
    NULLIF(TRIM('&2'), '') AS c_table,
    NULLIF(TRIM('&3'), '') AS c_ts
FROM dual;

VARIABLE object_owner VARCHAR2(128)
VARIABLE table_name   VARCHAR2(128)
VARIABLE target_ts    VARCHAR2(128)

DECLARE
    l_owner       VARCHAR2(128) := UPPER(TRIM('&&p_owner'));
    l_table_name  VARCHAR2(128) := UPPER(TRIM('&&p_table'));
    l_tablespace  VARCHAR2(128) := UPPER(TRIM('&&p_ts'));
    l_iot_type    dba_tables.iot_type%TYPE;
    l_cluster     dba_tables.cluster_name%TYPE;
    l_temporary   dba_tables.temporary%TYPE;
    l_nested      dba_tables.nested%TYPE;
    l_ts_count    PLS_INTEGER;
    l_ts_contents VARCHAR2(30);
    l_ts_status   VARCHAR2(9);
BEGIN
    IF l_table_name IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'Table name is required.');
    END IF;

    IF l_tablespace IS NULL THEN
        RAISE_APPLICATION_ERROR(-20002, 'Target tablespace is required.');
    END IF;

    IF NOT REGEXP_LIKE(l_owner, '^[A-Z][A-Z0-9_$#]*$')
       OR NOT REGEXP_LIKE(l_table_name, '^[A-Z][A-Z0-9_$#]*$')
       OR NOT REGEXP_LIKE(l_tablespace, '^[A-Z][A-Z0-9_$#]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'Owner, table, and tablespace must be ordinary Oracle identifiers.'
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

    BEGIN
        SELECT iot_type, cluster_name, temporary, nested
        INTO l_iot_type, l_cluster, l_temporary, l_nested
        FROM dba_tables
        WHERE owner = l_owner
          AND table_name = l_table_name;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
                -20007,
                'Table ' || l_owner || '.' || l_table_name || ' was not found.'
            );
    END;

    IF l_iot_type IS NOT NULL THEN
        RAISE_APPLICATION_ERROR(
            -20008,
            'IOT tables are not supported by this MOVE ONLINE script.'
        );
    END IF;

    IF l_cluster IS NOT NULL THEN
        RAISE_APPLICATION_ERROR(
            -20009,
            'Clustered tables are not supported by this MOVE ONLINE script.'
        );
    END IF;

    IF l_temporary = 'Y' THEN
        RAISE_APPLICATION_ERROR(-20010, 'Temporary tables cannot be moved.');
    END IF;

    IF l_nested = 'YES' THEN
        RAISE_APPLICATION_ERROR(-20011, 'Nested tables are not supported.');
    END IF;

    :object_owner := l_owner;
    :table_name   := l_table_name;
    :target_ts    := l_tablespace;
END;
/

COLUMN owner           FORMAT A16               HEADING 'Owner'
COLUMN table_name      FORMAT A30               HEADING 'Table'
COLUMN partitioned     FORMAT A4                HEADING 'Part'
COLUMN tablespace_name FORMAT A22               HEADING 'Tablespace'
COLUMN num_rows        FORMAT 999,999,999,990   HEADING 'Rows'
COLUMN blocks          FORMAT 999,999,990       HEADING 'Blocks'
COLUMN avg_row_len     FORMAT 999,990           HEADING 'Avg Row'
COLUMN last_analyzed   FORMAT A19               HEADING 'Last Analyzed'
COLUMN index_name      FORMAT A30               HEADING 'Index'
COLUMN uniqueness      FORMAT A10               HEADING 'Unique'
COLUMN status          FORMAT A10               HEADING 'Status'
COLUMN index_ts        FORMAT A22               HEADING 'Index Tablespace'

PROMPT
PROMPT === Table tablespace and statistics before move ===
PROMPT

SELECT
    t.owner,
    t.table_name,
    t.partitioned,
    t.tablespace_name,
    t.num_rows,
    t.blocks,
    t.avg_row_len,
    TO_CHAR(t.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS last_analyzed
FROM dba_tables t
WHERE t.owner = :object_owner
  AND t.table_name = :table_name;

PROMPT
PROMPT === Index status before move ===
PROMPT Indexes may become UNUSABLE if ONLINE cannot maintain them.
PROMPT Rebuild with rebuild_indexes.sql when STATUS is UNUSABLE.
PROMPT

SELECT
    i.index_name,
    i.uniqueness,
    i.status,
    i.tablespace_name AS index_ts
FROM dba_indexes i
WHERE i.table_owner = :object_owner
  AND i.table_name = :table_name
ORDER BY i.index_name;

PROMPT
PROMPT === MOVE ONLINE TABLESPACE ===
PROMPT

DECLARE
    l_owner      VARCHAR2(128) := :object_owner;
    l_table_name VARCHAR2(128) := :table_name;
    l_tablespace VARCHAR2(128) := :target_ts;
    l_partitioned dba_tables.partitioned%TYPE;
    l_sql        VARCHAR2(1000);
    l_attempted  PLS_INTEGER := 0;
    l_succeeded  PLS_INTEGER := 0;
    l_failed     PLS_INTEGER := 0;

    FUNCTION quote_name(p_name IN VARCHAR2) RETURN VARCHAR2 IS
    BEGIN
        RETURN '"' || REPLACE(p_name, '"', '""') || '"';
    END quote_name;

    PROCEDURE move_one(p_sql IN VARCHAR2) IS
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
    END move_one;
BEGIN
    SELECT partitioned
    INTO l_partitioned
    FROM dba_tables
    WHERE owner = l_owner
      AND table_name = l_table_name;

    DBMS_OUTPUT.PUT_LINE(
        'MOVE ONLINE TABLESPACE ' || l_tablespace
        || ' for ' || l_owner || '.' || l_table_name
    );
    DBMS_OUTPUT.PUT_LINE(RPAD('-', 78, '-'));

    IF l_partitioned = 'YES' THEN
        FOR part IN (
            SELECT partition_name,
                   composite
            FROM dba_tab_partitions
            WHERE table_owner = l_owner
              AND table_name = l_table_name
            ORDER BY partition_position
        ) LOOP
            IF part.composite = 'YES' THEN
                FOR sub IN (
                    SELECT subpartition_name
                    FROM dba_tab_subpartitions
                    WHERE table_owner = l_owner
                      AND table_name = l_table_name
                      AND partition_name = part.partition_name
                    ORDER BY subpartition_position
                ) LOOP
                    l_sql := 'ALTER TABLE ' || quote_name(l_owner) || '.'
                          || quote_name(l_table_name)
                          || ' MOVE SUBPARTITION '
                          || quote_name(sub.subpartition_name)
                          || ' ONLINE TABLESPACE '
                          || quote_name(l_tablespace);
                    move_one(l_sql);
                END LOOP;
            ELSE
                l_sql := 'ALTER TABLE ' || quote_name(l_owner) || '.'
                      || quote_name(l_table_name)
                      || ' MOVE PARTITION '
                      || quote_name(part.partition_name)
                      || ' ONLINE TABLESPACE '
                      || quote_name(l_tablespace);
                move_one(l_sql);
            END IF;
        END LOOP;
    ELSE
        l_sql := 'ALTER TABLE ' || quote_name(l_owner) || '.'
              || quote_name(l_table_name)
              || ' MOVE ONLINE TABLESPACE '
              || quote_name(l_tablespace);
        move_one(l_sql);
    END IF;

    DBMS_OUTPUT.PUT_LINE(RPAD('-', 78, '-'));
    DBMS_OUTPUT.PUT_LINE('Attempted: ' || l_attempted);
    DBMS_OUTPUT.PUT_LINE('Succeeded: ' || l_succeeded);
    DBMS_OUTPUT.PUT_LINE('Failed:    ' || l_failed);
END;
/

PROMPT
PROMPT === Table tablespace and statistics after move ===
PROMPT

SELECT
    t.owner,
    t.table_name,
    t.partitioned,
    t.tablespace_name,
    t.num_rows,
    t.blocks,
    t.avg_row_len,
    TO_CHAR(t.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS last_analyzed
FROM dba_tables t
WHERE t.owner = :object_owner
  AND t.table_name = :table_name;

PROMPT
PROMPT === Index status after move ===
PROMPT Rebuild UNUSABLE indexes with rebuild_indexes.sql.
PROMPT

SELECT
    i.index_name,
    i.uniqueness,
    i.status,
    i.tablespace_name AS index_ts
FROM dba_indexes i
WHERE i.table_owner = :object_owner
  AND i.table_name = :table_name
ORDER BY i.index_name;

UNDEFINE p_owner
UNDEFINE p_table
UNDEFINE p_ts
UNDEFINE 1
UNDEFINE 2
UNDEFINE 3

SET FEEDBACK ON
SET VERIFY ON
