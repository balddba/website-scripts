/*******************************************************************************
*
* Script Name: triggers.sql
* Title: List, enable, or disable triggers
* Tags: Triggers, Schema, Administration
* Purpose: Lists, enables, or disables selected Oracle triggers
*
* Description:
*   Lists, enables, or disables triggers for every table in a schema or for one
*   table. Triggers can be filtered by timing category. Each DDL statement is
*   shown, and failures are reported without stopping the remaining work.
*
* Parameters:
*   &1 - Action: LIST, ENABLE, or DISABLE
*   &2 - Target: SCHEMA.% or SCHEMA.TABLE_NAME
*   &3 - Trigger category: ALL, BEFORE, AFTER, INSTEAD_OF, or COMPOUND
*
* Required Privileges:
*   - SELECT on DBA_TRIGGERS
*   - Ownership of the selected triggers or ALTER ANY TRIGGER
*
* Output Format:
*   - Trigger status, type, and triggering event for LIST
*   - Each ALTER TRIGGER statement before ENABLE or DISABLE execution
*   - Success or Oracle error for each trigger
*   - Final attempted, succeeded, and failed counts
*
* Example Usage:
*   @triggers LIST HR.% ALL
*   @triggers DISABLE HR.% ALL
*   @triggers ENABLE HR.EMPLOYEES BEFORE
*   @triggers DISABLE APP.ORDERS COMPOUND
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
    l_category     VARCHAR2(30)  := UPPER(TRIM('&3'));
    l_owner        VARCHAR2(128);
    l_table_name   VARCHAR2(128);
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
    -- Reject invalid actions before querying or changing any triggers.
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

    -- Normalize the readable alias used for INSTEAD OF triggers.
    IF l_category = 'INSTEAD OF' THEN
        l_category := 'INSTEAD_OF';
    END IF;

    IF l_category NOT IN ('ALL', 'BEFORE', 'AFTER', 'INSTEAD_OF', 'COMPOUND') THEN
        RAISE_APPLICATION_ERROR(
            -20004,
            'Trigger category must be ALL, BEFORE, AFTER, INSTEAD_OF, or COMPOUND.'
        );
    END IF;

    DBMS_OUTPUT.PUT_LINE(
        l_action || ' triggers for ' || l_owner || '.' || l_table_name ||
        ' (category: ' || l_category || ')'
    );
    DBMS_OUTPUT.PUT_LINE(RPAD('-', 78, '-'));

    FOR trigger_rec IN (
        SELECT owner,
               trigger_name,
               table_name,
               trigger_type,
               triggering_event,
               status
        FROM dba_triggers
        WHERE owner = l_owner
          AND (l_table_name = '%' OR table_name = l_table_name)
          AND (l_action = 'LIST'
               OR status = CASE l_action
                               WHEN 'ENABLE' THEN 'DISABLED'
                               ELSE 'ENABLED'
                           END)
          AND (
              l_category = 'ALL'
              OR (l_category = 'BEFORE' AND trigger_type LIKE 'BEFORE%')
              OR (l_category = 'AFTER' AND trigger_type LIKE 'AFTER%')
              OR (l_category = 'INSTEAD_OF' AND trigger_type LIKE 'INSTEAD OF%')
              OR (l_category = 'COMPOUND' AND trigger_type = 'COMPOUND')
          )
        -- Oracle does not require dependency ordering when toggling triggers.
        ORDER BY NVL(table_name, CHR(255)), trigger_name
    ) LOOP
        l_attempted := l_attempted + 1;

        IF l_action = 'LIST' THEN
            DBMS_OUTPUT.PUT_LINE(
                trigger_rec.owner || '.' ||
                NVL(trigger_rec.table_name, '(schema/database)') ||
                '  ' || trigger_rec.trigger_name ||
                '  TYPE=' || trigger_rec.trigger_type ||
                '  EVENT=' || trigger_rec.triggering_event ||
                '  STATUS=' || trigger_rec.status
            );
        ELSE
            -- ALTER TRIGGER also supports schema-level and database-level triggers.
            l_sql := 'ALTER TRIGGER ' || quote_name(trigger_rec.owner) || '.' ||
                     quote_name(trigger_rec.trigger_name) || ' ' || l_action;

            DBMS_OUTPUT.PUT_LINE(
                l_sql || '; -- ' || trigger_rec.trigger_type ||
                ' ON ' || NVL(trigger_rec.table_name, '(schema/database)') ||
                ': ' || trigger_rec.triggering_event
            );
            BEGIN
                EXECUTE IMMEDIATE l_sql;
                l_succeeded := l_succeeded + 1;
                DBMS_OUTPUT.PUT_LINE('  OK');
            EXCEPTION
                WHEN OTHERS THEN
                    -- Continue so one privilege or object error does not hide later results.
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
            DBMS_OUTPUT.PUT_LINE('No matching triggers found.');
        ELSE
            DBMS_OUTPUT.PUT_LINE('No matching triggers required a status change.');
        END IF;
    END IF;
END;
/

SET FEEDBACK ON
