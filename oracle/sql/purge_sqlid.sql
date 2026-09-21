/*******************************************************************************
*
* Script Name: purge_sqlid.sql
* Title: Purge a SQL_ID from the shared pool
* Tags: SQL, Shared Pool, Cursors
* Purpose: Flush one SQL_ID's cursor heaps from the current instance library cache
*
* Description:
*   Looks up the SQL_ID in GV$SQL, then calls DBMS_SHARED_POOL.PURGE with flag
*   C for each distinct address and hash_value on this instance. That drops
*   the parent cursor and its children from the local shared pool so the next
*   execution hard-parses again. RAC instances do not share a library cache;
*   run the script on every instance that still holds the cursor. Sessions
*   executing the statement can reload it immediately. This does not remove
*   the statement from AWR, SQL tuning sets, or the other PDBs.
*
* Parameters:
*   &1 - Required SQL_ID (13 characters)
*
* Required Privileges:
*   - EXECUTE on DBMS_SHARED_POOL
*   - SELECT on GV$SQL
*   - SELECT on V$SQL
*   - SELECT on V$INSTANCE
*
* Output Format:
*   - Matching cursors on every RAC instance before the purge
*   - One OK or FAIL line per purged heap
*   - Remaining cursors after the purge
*
* Example Usage:
*   SQL> @purge_sqlid.sql 8zxfktj5s7k8m
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET SERVEROUTPUT ON SIZE UNLIMITED
SET LINESIZE 220
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN c_sqlid NEW_VALUE p_sqlid NOPRINT
SELECT LOWER(TRIM('&1')) AS c_sqlid FROM dual;

COLUMN inst_id            FORMAT 999              HEADING 'Inst'
COLUMN child_number       FORMAT 9999             HEADING 'Child'
COLUMN parsing_schema_name FORMAT A20             HEADING 'Schema'
COLUMN plan_hash_value    FORMAT 9999999999       HEADING 'Plan Hash'
COLUMN executions         FORMAT 999,999,999      HEADING 'Execs'
COLUMN users_opening      FORMAT 9999             HEADING 'Open'
COLUMN users_executing    FORMAT 9999             HEADING 'Exec'
COLUMN last_active_time   FORMAT A19              HEADING 'Last Active'
COLUMN sql_text           FORMAT A50 TRUNC        HEADING 'SQL Text'

PROMPT
PROMPT === Cursors for SQL_ID &&p_sqlid (all instances) ===
PROMPT

SELECT
    inst_id,
    child_number,
    parsing_schema_name,
    plan_hash_value,
    executions,
    users_opening,
    users_executing,
    last_active_time,
    sql_text
FROM gv$sql
WHERE sql_id = '&&p_sqlid'
ORDER BY inst_id, child_number;

DECLARE
    v_sqlid          VARCHAR2(64) := LOWER(TRIM('&&p_sqlid'));
    v_inst_id        NUMBER;
    v_inst_name      VARCHAR2(64);
    v_local_children NUMBER;
    v_executing      NUMBER;
    v_purged         NUMBER := 0;
    v_failed         NUMBER := 0;
    v_remaining      NUMBER;
    v_other_inst     NUMBER;
    v_name           VARCHAR2(128);
    v_anywhere       NUMBER;

    PROCEDURE emit(p_msg VARCHAR2) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(p_msg);
    END emit;
BEGIN
    IF v_sqlid IS NULL OR NOT REGEXP_LIKE(v_sqlid, '^[0-9a-z]{13}$') THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'SQL_ID must be a 13-character identifier (digits and lowercase letters).'
        );
    END IF;

    SELECT instance_number, instance_name
    INTO v_inst_id, v_inst_name
    FROM v$instance;

    SELECT COUNT(*), NVL(SUM(users_executing), 0)
    INTO v_local_children, v_executing
    FROM v$sql
    WHERE sql_id = v_sqlid;

    IF v_local_children = 0 THEN
        SELECT COUNT(*)
        INTO v_anywhere
        FROM gv$sql
        WHERE sql_id = v_sqlid;

        IF v_anywhere = 0 THEN
            RAISE_APPLICATION_ERROR(
                -20002,
                'SQL_ID ' || v_sqlid || ' is not in the shared pool on any instance.'
            );
        END IF;

        emit(
            'No local cursors for ' || v_sqlid
            || ' on instance ' || v_inst_id || ' (' || v_inst_name || ').'
        );
        emit('The cursor exists on other RAC instances. Run this script there.');
        RETURN;
    END IF;

    emit(
        'Purging SQL_ID ' || v_sqlid
        || ' from instance ' || v_inst_id || ' (' || v_inst_name || ')...'
    );

    IF v_executing > 0 THEN
        emit(
            'WARNING: ' || v_executing
            || ' session(s) are executing this SQL. The cursor may reload immediately.'
        );
    END IF;

    FOR rec IN (
        SELECT DISTINCT address, hash_value
        FROM v$sql
        WHERE sql_id = v_sqlid
    ) LOOP
        v_name := rec.address || ',' || rec.hash_value;
        BEGIN
            DBMS_SHARED_POOL.PURGE(v_name, 'C');
            v_purged := v_purged + 1;
            emit('OK   ' || v_name);
        EXCEPTION
            WHEN OTHERS THEN
                v_failed := v_failed + 1;
                emit('FAIL ' || v_name || ' -> ' || SQLERRM);
        END;
    END LOOP;

    SELECT COUNT(*)
    INTO v_remaining
    FROM v$sql
    WHERE sql_id = v_sqlid;

    SELECT COUNT(DISTINCT inst_id)
    INTO v_other_inst
    FROM gv$sql
    WHERE sql_id = v_sqlid
      AND inst_id <> v_inst_id;

    emit(
        'Purged heaps: ' || v_purged
        || '  Failed: ' || v_failed
        || '  Remaining local children: ' || v_remaining
    );

    IF v_other_inst > 0 THEN
        emit(
            'Other instances still hold this SQL_ID ('
            || v_other_inst || '). Run this script on each of them.'
        );
    END IF;
END;
/

PROMPT
PROMPT === Cursors remaining for SQL_ID &&p_sqlid ===
PROMPT

SELECT
    inst_id,
    child_number,
    parsing_schema_name,
    plan_hash_value,
    executions,
    users_opening,
    users_executing,
    last_active_time,
    sql_text
FROM gv$sql
WHERE sql_id = '&&p_sqlid'
ORDER BY inst_id, child_number;

COLUMN inst_id CLEAR
COLUMN child_number CLEAR
COLUMN parsing_schema_name CLEAR
COLUMN plan_hash_value CLEAR
COLUMN executions CLEAR
COLUMN users_opening CLEAR
COLUMN users_executing CLEAR
COLUMN last_active_time CLEAR
COLUMN sql_text CLEAR
COLUMN c_sqlid CLEAR

UNDEFINE p_sqlid

SET FEEDBACK ON
SET VERIFY ON
