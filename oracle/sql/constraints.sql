/*******************************************************************************
*
* Script Name: constraints.sql
* Title: List, enable, or disable constraints
* Tags: Constraints, Schema, Administration
* Purpose: Lists, enables, or disables selected Oracle constraints
*
* Description:
*   Lists, enables, or disables constraints for every table in a schema or for
*   one table. Parent keys and foreign keys are processed in an order that
*   avoids dependency errors within the requested scope. Each DDL statement is
*   shown, and failures are reported without stopping the remaining work.
*
* Parameters:
*   &1 - Action: LIST, ENABLE, or DISABLE
*   &2 - Target: SCHEMA.% or SCHEMA.TABLE_NAME
*   &3 - Constraint type: ALL, P, U, R, C, PRIMARY_KEY, UNIQUE,
*        FOREIGN_KEY, or CHECK
*
* Required Privileges:
*   - SELECT on DBA_CONSTRAINTS
*   - ALTER privilege on every selected table
*
* Output Format:
*   - Constraint status and validation details for LIST
*   - Each ALTER TABLE statement before ENABLE or DISABLE execution
*   - Success or Oracle error for each constraint
*   - Final attempted, succeeded, and failed counts
*
* Example Usage:
*   @constraints LIST HR.% ALL
*   @constraints DISABLE HR.% ALL
*   @constraints ENABLE HR.EMPLOYEES FOREIGN_KEY
*   @constraints DISABLE APP.ORDERS C
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET SERVEROUTPUT ON SIZE UNLIMITED
SET VERIFY OFF
SET FEEDBACK OFF

DECLARE
    l_action       VARCHAR2(7)   := UPPER(TRIM('&1'));
    l_target       VARCHAR2(261) := UPPER(TRIM('&2'));
    l_type_input   VARCHAR2(30)  := UPPER(TRIM('&3'));
    l_owner        VARCHAR2(128);
    l_table_name   VARCHAR2(128);
    l_type         VARCHAR2(1);
    l_dot_position PLS_INTEGER;
    l_sql          VARCHAR2(1000);
    l_attempted    PLS_INTEGER := 0;
    l_succeeded    PLS_INTEGER := 0;
    l_failed       PLS_INTEGER := 0;

    -- Quote names read from the data dictionary before placing them in DDL.
    FUNCTION quote_name(p_name IN VARCHAR2) RETURN VARCHAR2 IS
    BEGIN
        RETURN '"' || REPLACE(p_name, '"', '""') || '"';
    END quote_name;
BEGIN
    -- Reject invalid actions before querying or changing any constraints.
    IF l_action NOT IN ('LIST', 'ENABLE', 'DISABLE') THEN
        RAISE_APPLICATION_ERROR(-20001, 'Action must be LIST, ENABLE, or DISABLE.');
    END IF;

    -- Split the required SCHEMA.TABLE target into dictionary lookup values.
    l_dot_position := INSTR(l_target, '.');
    IF l_dot_position <= 1
       OR l_dot_position = LENGTH(l_target)
       OR INSTR(l_target, '.', l_dot_position + 1) > 0 THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Target must be in SCHEMA.% or SCHEMA.TABLE_NAME format.'
        );
    END IF;

    l_owner      := SUBSTR(l_target, 1, l_dot_position - 1);
    l_table_name := SUBSTR(l_target, l_dot_position + 1);

    -- Only the table portion may use %, and only as the complete table value.
    IF NOT REGEXP_LIKE(l_owner, '^[A-Z][A-Z0-9_$#]*$')
       OR (l_table_name <> '%'
           AND NOT REGEXP_LIKE(l_table_name, '^[A-Z][A-Z0-9_$#]*$')) THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'Schema and table must be ordinary Oracle identifiers; only % is supported as a wildcard.'
        );
    END IF;

    -- Normalize readable names and Oracle's one-character type codes.
    l_type := CASE l_type_input
        WHEN 'P'           THEN 'P'
        WHEN 'PRIMARY_KEY' THEN 'P'
        WHEN 'PRIMARY KEY' THEN 'P'
        WHEN 'U'           THEN 'U'
        WHEN 'UNIQUE'      THEN 'U'
        WHEN 'R'           THEN 'R'
        WHEN 'FOREIGN_KEY' THEN 'R'
        WHEN 'FOREIGN KEY' THEN 'R'
        WHEN 'C'           THEN 'C'
        WHEN 'CHECK'       THEN 'C'
        WHEN 'ALL'         THEN NULL
        ELSE 'X'
    END;

    IF l_type = 'X' THEN
        RAISE_APPLICATION_ERROR(
            -20004,
            'Constraint type must be ALL, P, U, R, C, PRIMARY_KEY, UNIQUE, FOREIGN_KEY, or CHECK.'
        );
    END IF;

    DBMS_OUTPUT.PUT_LINE(
        l_action || ' constraints for ' || l_owner || '.' || l_table_name ||
        ' (type: ' || l_type_input || ')'
    );
    DBMS_OUTPUT.PUT_LINE(RPAD('-', 78, '-'));

    FOR constraint_rec IN (
        SELECT owner,
               table_name,
               constraint_name,
               constraint_type,
               status,
               validated
        FROM dba_constraints
        WHERE owner = l_owner
          AND (l_table_name = '%' OR table_name = l_table_name)
          AND constraint_type IN ('P', 'U', 'R', 'C')
          AND (l_type IS NULL OR constraint_type = l_type)
          AND (l_action = 'LIST'
               OR status = CASE l_action
                               WHEN 'ENABLE' THEN 'DISABLED'
                               ELSE 'ENABLED'
                           END)
        ORDER BY
            -- Disable children first; enable referenced parent keys first.
            CASE
                WHEN l_action = 'DISABLE' AND constraint_type = 'R' THEN 10
                WHEN l_action = 'DISABLE' AND constraint_type = 'C' THEN 20
                WHEN l_action = 'DISABLE' AND constraint_type IN ('P', 'U') THEN 30
                WHEN l_action = 'ENABLE'  AND constraint_type IN ('P', 'U') THEN 10
                WHEN l_action = 'ENABLE'  AND constraint_type = 'C' THEN 20
                WHEN l_action = 'ENABLE'  AND constraint_type = 'R' THEN 30
                ELSE 40
            END,
            table_name,
            constraint_name
    ) LOOP
        l_attempted := l_attempted + 1;

        IF l_action = 'LIST' THEN
            DBMS_OUTPUT.PUT_LINE(
                constraint_rec.owner || '.' || constraint_rec.table_name ||
                '  ' || constraint_rec.constraint_name ||
                '  TYPE=' || constraint_rec.constraint_type ||
                '  STATUS=' || constraint_rec.status ||
                '  VALIDATED=' || constraint_rec.validated
            );
        ELSE
            -- Dictionary identifiers are quoted to preserve names and special characters.
            l_sql := 'ALTER TABLE ' || quote_name(constraint_rec.owner) || '.' ||
                     quote_name(constraint_rec.table_name) || ' ' || l_action ||
                     ' CONSTRAINT ' || quote_name(constraint_rec.constraint_name);

            DBMS_OUTPUT.PUT_LINE(l_sql || ';');
            BEGIN
                EXECUTE IMMEDIATE l_sql;
                l_succeeded := l_succeeded + 1;
                DBMS_OUTPUT.PUT_LINE('  OK');
            EXCEPTION
                WHEN OTHERS THEN
                    -- Continue so one data or dependency error does not hide later results.
                    l_failed := l_failed + 1;
                    DBMS_OUTPUT.PUT_LINE('  ERROR ' || SQLCODE || ': ' || SQLERRM);
            END;
        END IF;
    END LOOP;

    DBMS_OUTPUT.PUT_LINE(RPAD('-', 78, '-'));
    IF l_action = 'LIST' THEN
        DBMS_OUTPUT.PUT_LINE('Matched: ' || l_attempted);
    ELSE
        DBMS_OUTPUT.PUT_LINE('Attempted: ' || l_attempted);
        DBMS_OUTPUT.PUT_LINE('Succeeded: ' || l_succeeded);
        DBMS_OUTPUT.PUT_LINE('Failed:    ' || l_failed);
    END IF;

    IF l_attempted = 0 THEN
        IF l_action = 'LIST' THEN
            DBMS_OUTPUT.PUT_LINE('No matching constraints found.');
        ELSE
            DBMS_OUTPUT.PUT_LINE('No matching constraints required a status change.');
        END IF;
    END IF;

    IF l_action <> 'LIST' AND l_failed > 0 THEN
        DBMS_OUTPUT.PUT_LINE(
            'Review failures above. A common cause is a referencing foreign key outside the requested scope.'
        );
    END IF;
END;
/

SET FEEDBACK ON
