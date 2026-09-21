/*******************************************************************************
*
* Script Name: compile.sql
* Title: Compile invalid objects
* Tags: Invalid Objects, PL/SQL, Compile
* Purpose: Compile invalid objects for a schema, a single object, or the whole database
*
* Description:
*   Recompiles invalid objects with the correct ALTER statement per type
*   (packages and type bodies, views, synonyms, materialized views, Java,
*   and so on). Several passes run so dependents can compile after their
*   referenced objects. Target uses LIKE wildcards: SCHEMA compiles every
*   invalid object in that schema, SCHEMA.% does the same, SCHEMA.OBJECT
*   compiles that object, and % compiles all non-Oracle-maintained schemas.
*   Press Enter at the SQL*Plus prompt if no argument is passed.
*
* Parameters:
*   &1 - (Optional) Target: SCHEMA | SCHEMA.% | SCHEMA.OBJECT | %
*        Default is % (all non-Oracle-maintained invalid objects)
*
* Required Privileges:
*   - SELECT on DBA_OBJECTS
*   - SELECT on DBA_USERS
*   - SELECT on DBA_ERRORS
*   - ALTER on the object types being compiled (DBA or ALTER ANY ...)
*
* Output Format:
*   - Each compile attempt with OK, FAIL, or SKIP
*   - Pass counts and a remaining-invalid list with the first error
*
* Example Usage:
*   SQL> @compile.sql %
*   SQL> @compile.sql HR
*   SQL> @compile.sql HR.%
*   SQL> @compile.sql HR.EMP_PKG
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET SERVEROUTPUT ON SIZE UNLIMITED
SET LINESIZE 220

-- Optional &1: SQL*Plus prompts if omitted; Enter (empty) means compile all (%).
COLUMN c_target NEW_VALUE p_target NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), '%') AS c_target FROM dual;

DECLARE
    -- Dependents often stay invalid until the object they call compiles.
    c_max_passes CONSTANT PLS_INTEGER := 8;

    v_raw          VARCHAR2(257) := TRIM('&&p_target');
    v_schema_pat   VARCHAR2(128);
    v_object_pat   VARCHAR2(128);
    v_all_schemas  VARCHAR2(1);   -- Y when target schema is %, skip Oracle-owned schemas
    v_pass         PLS_INTEGER := 0;
    v_ok           PLS_INTEGER := 0;
    v_skip         PLS_INTEGER := 0;
    v_pass_ok      PLS_INTEGER;
    v_found        PLS_INTEGER := 0;
    v_remaining    PLS_INTEGER := 0;
    v_ddl          VARCHAR2(1000);
    v_status       VARCHAR2(10);
    v_err          VARCHAR2(4000);
    v_ident        VARCHAR2(300);

    -- Invalid, compilable objects matching the target. Partition/subobject
    -- rows are skipped; compile the parent object instead.
    CURSOR c_invalid(
        cp_owner       VARCHAR2,
        cp_name        VARCHAR2,
        cp_all_schemas VARCHAR2
    ) IS
        SELECT
            o.owner,
            o.object_name,
            o.object_type
        FROM dba_objects o
        WHERE o.status = 'INVALID'
          AND o.subobject_name IS NULL
          -- LIKE treats '_' as a wildcard; HR.EMP_PKG must not match EMPXPKG.
          -- Use equality unless the pattern actually contains '%'.
          AND (
                (INSTR(cp_owner, '%') = 0 AND o.owner = cp_owner)
                OR (INSTR(cp_owner, '%') > 0 AND o.owner LIKE cp_owner)
              )
          AND (
                (INSTR(cp_name, '%') = 0 AND o.object_name = cp_name)
                OR (INSTR(cp_name, '%') > 0 AND o.object_name LIKE cp_name)
              )
          AND o.object_type IN (
                'SYNONYM',
                'TYPE',
                'TYPE BODY',
                'OPERATOR',
                'INDEXTYPE',
                'LIBRARY',
                'VIEW',
                'FUNCTION',
                'PROCEDURE',
                'PACKAGE',
                'PACKAGE BODY',
                'TRIGGER',
                'MATERIALIZED VIEW',
                'DIMENSION',
                'JAVA SOURCE',
                'JAVA CLASS'
              )
          -- '%' (whole database) skips SYS/MDSYS/etc. An explicit SYS target is honored.
          AND (
                cp_all_schemas = 'N'
                OR o.owner = 'PUBLIC'
                OR EXISTS (
                    SELECT 1
                    FROM dba_users u
                    WHERE u.username = o.owner
                      AND u.oracle_maintained = 'N'
                )
              )
        ORDER BY
            -- Specs before bodies, synonyms/types before PL/SQL that depends on them.
            DECODE(
                o.object_type,
                'SYNONYM', 1,
                'TYPE', 2,
                'TYPE BODY', 3,
                'OPERATOR', 4,
                'INDEXTYPE', 5,
                'LIBRARY', 6,
                'VIEW', 7,
                'FUNCTION', 8,
                'PROCEDURE', 9,
                'PACKAGE', 10,
                'PACKAGE BODY', 11,
                'TRIGGER', 12,
                'MATERIALIZED VIEW', 13,
                'DIMENSION', 14,
                'JAVA SOURCE', 15,
                'JAVA CLASS', 16,
                99
            ),
            o.owner,
            o.object_name;

    -- Quote dictionary names so reserved words and mixed-case identifiers compile.
    FUNCTION quoted_name(p_name VARCHAR2) RETURN VARCHAR2 IS
    BEGIN
        RETURN '"' || REPLACE(p_name, '"', '""') || '"';
    END quoted_name;

    FUNCTION qualified(p_owner VARCHAR2, p_name VARCHAR2) RETURN VARCHAR2 IS
    BEGIN
        RETURN quoted_name(p_owner) || '.' || quoted_name(p_name);
    END qualified;

    -- Each object type uses a different ALTER ... COMPILE form.
    -- PACKAGE BODY / TYPE BODY compile the body, not the spec.
    FUNCTION compile_ddl(
        p_owner VARCHAR2,
        p_name  VARCHAR2,
        p_type  VARCHAR2
    ) RETURN VARCHAR2 IS
        v_q VARCHAR2(300) := qualified(p_owner, p_name);
    BEGIN
        CASE p_type
            WHEN 'PROCEDURE' THEN
                RETURN 'ALTER PROCEDURE ' || v_q || ' COMPILE';
            WHEN 'FUNCTION' THEN
                RETURN 'ALTER FUNCTION ' || v_q || ' COMPILE';
            WHEN 'PACKAGE' THEN
                RETURN 'ALTER PACKAGE ' || v_q || ' COMPILE';
            WHEN 'PACKAGE BODY' THEN
                RETURN 'ALTER PACKAGE ' || v_q || ' COMPILE BODY';
            WHEN 'TRIGGER' THEN
                RETURN 'ALTER TRIGGER ' || v_q || ' COMPILE';
            WHEN 'VIEW' THEN
                RETURN 'ALTER VIEW ' || v_q || ' COMPILE';
            WHEN 'TYPE' THEN
                RETURN 'ALTER TYPE ' || v_q || ' COMPILE';
            WHEN 'TYPE BODY' THEN
                RETURN 'ALTER TYPE ' || v_q || ' COMPILE BODY';
            WHEN 'SYNONYM' THEN
                -- PUBLIC is a namespace, not a schema; ALTER SYNONYM PUBLIC.x is invalid.
                IF p_owner = 'PUBLIC' THEN
                    RETURN 'ALTER PUBLIC SYNONYM ' || quoted_name(p_name) || ' COMPILE';
                END IF;
                RETURN 'ALTER SYNONYM ' || v_q || ' COMPILE';
            WHEN 'MATERIALIZED VIEW' THEN
                RETURN 'ALTER MATERIALIZED VIEW ' || v_q || ' COMPILE';
            WHEN 'LIBRARY' THEN
                RETURN 'ALTER LIBRARY ' || v_q || ' COMPILE';
            WHEN 'DIMENSION' THEN
                RETURN 'ALTER DIMENSION ' || v_q || ' COMPILE';
            WHEN 'OPERATOR' THEN
                RETURN 'ALTER OPERATOR ' || v_q || ' COMPILE';
            WHEN 'INDEXTYPE' THEN
                RETURN 'ALTER INDEXTYPE ' || v_q || ' COMPILE';
            WHEN 'JAVA CLASS' THEN
                RETURN 'ALTER JAVA CLASS ' || v_q || ' COMPILE';
            WHEN 'JAVA SOURCE' THEN
                RETURN 'ALTER JAVA SOURCE ' || v_q || ' COMPILE';
            ELSE
                RETURN NULL;
        END CASE;
    END compile_ddl;

    -- ALTER COMPILE can return without raising and still leave the object INVALID
    -- (SQL*Plus would show "altered with compilation errors"). Always re-read status.
    FUNCTION object_status(
        p_owner VARCHAR2,
        p_name  VARCHAR2,
        p_type  VARCHAR2
    ) RETURN VARCHAR2 IS
        v_st VARCHAR2(10);
    BEGIN
        SELECT status
        INTO v_st
        FROM dba_objects
        WHERE owner = p_owner
          AND object_name = p_name
          AND object_type = p_type
          AND subobject_name IS NULL
          AND ROWNUM = 1;
        RETURN v_st;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN NULL;
    END object_status;

    -- First compiler error for the remaining-invalid report (ORA-24344 is not useful).
    FUNCTION first_error(
        p_owner VARCHAR2,
        p_name  VARCHAR2,
        p_type  VARCHAR2
    ) RETURN VARCHAR2 IS
        v_text VARCHAR2(4000);
        v_type VARCHAR2(30) :=
            CASE
                WHEN p_type IN ('PACKAGE', 'PACKAGE BODY') THEN p_type
                WHEN p_type IN ('TYPE', 'TYPE BODY') THEN p_type
                ELSE p_type
            END;
    BEGIN
        SELECT SUBSTR(MAX(text) KEEP (DENSE_RANK FIRST ORDER BY sequence), 1, 400)
        INTO v_text
        FROM dba_errors
        WHERE owner = p_owner
          AND name = p_name
          AND attribute = 'ERROR'
          AND (
                type = v_type
                OR (v_type = 'PACKAGE BODY' AND type = 'PACKAGE BODY')
                OR (v_type = 'TYPE BODY' AND type = 'TYPE BODY')
              );
        RETURN v_text;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN NULL;
    END first_error;

    PROCEDURE emit(p_msg VARCHAR2) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(p_msg);
    END emit;
BEGIN
    -- SCHEMA, SCHEMA.OBJECT, SCHEMA.%, or %. Treat * the same as %.
    v_raw := REPLACE(NVL(v_raw, '%'), '*', '%');
    v_raw := UPPER(v_raw);

    IF INSTR(v_raw, '.') > 0 THEN
        v_schema_pat := SUBSTR(v_raw, 1, INSTR(v_raw, '.') - 1);
        v_object_pat := SUBSTR(v_raw, INSTR(v_raw, '.') + 1);
    ELSE
        -- Bare schema name means every invalid object in that schema.
        v_schema_pat := v_raw;
        v_object_pat := '%';
    END IF;

    IF v_schema_pat IS NULL THEN
        v_schema_pat := '%';
    END IF;
    IF v_object_pat IS NULL THEN
        v_object_pat := '%';
    END IF;

    v_all_schemas := CASE WHEN v_schema_pat = '%' THEN 'Y' ELSE 'N' END;

    emit('Target: ' || v_schema_pat || '.' || v_object_pat);
    IF v_all_schemas = 'Y' THEN
        emit('Scope:  all invalid objects in non-Oracle-maintained schemas');
    END IF;
    emit('----------------------------------------------------------------------');

    FOR rec IN c_invalid(v_schema_pat, v_object_pat, v_all_schemas) LOOP
        v_found := v_found + 1;
    END LOOP;

    IF v_found = 0 THEN
        emit('No invalid objects matched this target.');
        -- Only for a fully qualified name: distinguish "already valid" from "does not exist".
        IF INSTR(v_schema_pat, '%') = 0 AND INSTR(v_object_pat, '%') = 0 THEN
            SELECT COUNT(*)
            INTO v_found
            FROM dba_objects
            WHERE owner = v_schema_pat
              AND object_name = v_object_pat
              AND subobject_name IS NULL;
            IF v_found > 0 THEN
                emit('Matching objects exist and are already VALID.');
            ELSE
                emit('No objects found for this target.');
            END IF;
        END IF;
        RETURN;
    END IF;

    emit('Invalid objects to compile: ' || v_found);

    -- Re-query invalid objects each pass. Stop when a pass compiles nothing new.
    LOOP
        v_pass := v_pass + 1;
        v_pass_ok := 0;
        emit(CHR(10) || 'Pass ' || v_pass);

        FOR rec IN c_invalid(v_schema_pat, v_object_pat, v_all_schemas) LOOP
            v_ident := rec.owner || '.' || rec.object_name;
            v_ddl := compile_ddl(rec.owner, rec.object_name, rec.object_type);

            IF v_ddl IS NULL THEN
                v_skip := v_skip + 1;
                emit('SKIP  ' || RPAD(rec.object_type, 18) || ' ' || v_ident);
                CONTINUE;
            END IF;

            v_err := NULL;
            BEGIN
                EXECUTE IMMEDIATE v_ddl;
            EXCEPTION
                -- ORA-24344 (compiled with errors) and missing-privilege errors land here.
                WHEN OTHERS THEN
                    v_err := SQLERRM;
            END;

            v_status := object_status(rec.owner, rec.object_name, rec.object_type);
            IF v_status = 'VALID' THEN
                v_ok := v_ok + 1;
                v_pass_ok := v_pass_ok + 1;
                emit('OK    ' || RPAD(rec.object_type, 18) || ' ' || v_ident);
            ELSE
                v_err := NVL(first_error(rec.owner, rec.object_name, rec.object_type), v_err);
                emit(
                    'FAIL  ' || RPAD(rec.object_type, 18) || ' ' || v_ident
                    || CASE WHEN v_err IS NOT NULL THEN ' -> ' || v_err END
                );
            END IF;
            v_err := NULL;
        END LOOP;

        EXIT WHEN v_pass_ok = 0 OR v_pass >= c_max_passes;
    END LOOP;

    FOR rec IN c_invalid(v_schema_pat, v_object_pat, v_all_schemas) LOOP
        v_remaining := v_remaining + 1;
    END LOOP;

    emit(CHR(10) || '----------------------------------------------------------------------');
    emit('Passes:         ' || v_pass);
    emit('Compiled valid: ' || v_ok);
    emit('Skipped:        ' || v_skip);
    emit('Still invalid:  ' || v_remaining);

    IF v_remaining > 0 THEN
        emit(CHR(10) || 'Remaining invalid objects:');
        FOR rec IN c_invalid(v_schema_pat, v_object_pat, v_all_schemas) LOOP
            v_err := first_error(rec.owner, rec.object_name, rec.object_type);
            emit(
                '  ' || RPAD(rec.object_type, 18) || ' '
                || rec.owner || '.' || rec.object_name
                || CASE WHEN v_err IS NOT NULL THEN ' -> ' || v_err END
            );
        END LOOP;
    END IF;
END;
/

UNDEFINE p_target
UNDEFINE 1
SET FEEDBACK ON
