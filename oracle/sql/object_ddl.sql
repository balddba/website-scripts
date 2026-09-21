/*******************************************************************************
*
* Script Name: object_ddl.sql
* Title: Object DDL
* Tags: DDL, Metadata
* Purpose: Print DBMS_METADATA.GET_DDL for an object in SQL*Plus
*
* Description:
*   Emits CREATE DDL for one dictionary object. SESSION_TRANSFORM is set to
*   PRETTY and SQLTERMINATOR so the output is indented and ends with a
*   semicolon. Object type uses DBMS_METADATA names (TABLE, INDEX, VIEW,
*   PACKAGE, PACKAGE_BODY, and so on); a space in the type is converted to
*   an underscore. SET LONG controls how much of the CLOB is printed.
*
* Parameters:
*   &1 - Object type (required), for example TABLE, INDEX, VIEW, PACKAGE
*   &2 - Owner. Default: current USER
*   &3 - Object name (required)
*
* Required Privileges:
*   - EXECUTE on DBMS_METADATA
*   - SELECT on DBA_OBJECTS
*   - SELECT_CATALOG_ROLE, or ownership of the object
*
* Output Format:
*   - Pretty-printed DDL with a SQL terminator
*
* Example Usage:
*   SQL> @object_ddl.sql TABLE HR EMPLOYEES
*   SQL> @object_ddl.sql INDEX HR EMP_EMP_ID_PK
*   SQL> @object_ddl.sql PACKAGE_BODY HR EMP_PKG
*   SQL> @object_ddl.sql "PACKAGE BODY" HR EMP_PKG
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET ECHO OFF
SET LINESIZE 200
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF
SET WRAP ON

-- Optional &2: SQL*Plus prompts if omitted; Enter uses current USER.
COLUMN c_type  NEW_VALUE p_type  NOPRINT
COLUMN c_owner NEW_VALUE p_owner NOPRINT
COLUMN c_name  NEW_VALUE p_name  NOPRINT
SELECT
    NULLIF(TRIM('&1'), '') AS c_type,
    NVL(CAST(TRIM('&2') AS VARCHAR2(128)), USER) AS c_owner,
    NULLIF(TRIM('&3'), '') AS c_name
FROM dual;

VARIABLE object_type  VARCHAR2(30)
VARIABLE object_owner VARCHAR2(128)
VARIABLE object_name  VARCHAR2(128)

DECLARE
    l_type        VARCHAR2(30)  := UPPER(TRIM('&&p_type'));
    l_owner       VARCHAR2(128) := UPPER(TRIM('&&p_owner'));
    l_object_name VARCHAR2(128) := UPPER(TRIM('&&p_name'));
    l_count       PLS_INTEGER;
BEGIN
    IF l_type IS NULL THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Object type is required (TABLE, INDEX, VIEW, PACKAGE, PACKAGE_BODY, ...).'
        );
    END IF;

    IF l_object_name IS NULL THEN
        RAISE_APPLICATION_ERROR(-20002, 'Object name is required.');
    END IF;

    l_type := REPLACE(l_type, ' ', '_');

    IF NOT REGEXP_LIKE(l_owner, '^[A-Z][A-Z0-9_$#]*$')
       OR NOT REGEXP_LIKE(l_object_name, '^[A-Z][A-Z0-9_$#]*$')
       OR NOT REGEXP_LIKE(l_type, '^[A-Z][A-Z0-9_]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'Object type, owner, and name must be ordinary Oracle identifiers.'
        );
    END IF;

    SELECT COUNT(*)
    INTO l_count
    FROM dba_objects
    WHERE owner = l_owner
      AND object_name = l_object_name
      AND object_type = REPLACE(l_type, '_', ' ')
      AND subobject_name IS NULL;

    IF l_count = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20004,
            'Object ' || l_type || ' ' || l_owner || '.' || l_object_name
            || ' was not found.'
        );
    END IF;

    :object_type  := l_type;
    :object_owner := l_owner;
    :object_name  := l_object_name;

    DBMS_METADATA.SET_TRANSFORM_PARAM(
        DBMS_METADATA.SESSION_TRANSFORM,
        'PRETTY',
        TRUE
    );
    DBMS_METADATA.SET_TRANSFORM_PARAM(
        DBMS_METADATA.SESSION_TRANSFORM,
        'SQLTERMINATOR',
        TRUE
    );
END;
/

SET HEADING OFF
SET PAGESIZE 0
SET LONG 1000000
SET LONGCHUNKSIZE 32767

COLUMN ddl_text FORMAT A200

SELECT DBMS_METADATA.GET_DDL(:object_type, :object_name, :object_owner) AS ddl_text
FROM dual;

UNDEFINE p_type
UNDEFINE p_owner
UNDEFINE p_name
UNDEFINE 1
UNDEFINE 2
UNDEFINE 3

SET HEADING ON
SET PAGESIZE 100
SET FEEDBACK ON
SET VERIFY ON
