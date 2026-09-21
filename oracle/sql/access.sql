/*******************************************************************************
*
* Script Name: access.sql
* Title: Object access paths
* Tags: Security, Grants, Privileges
* Purpose: Show who can use an object through a direct grant, a role, or a system privilege
*
* Description:
*   Reports access to one Oracle object. Direct grants come from DBA_TAB_PRIVS
*   and DBA_COL_PRIVS. Role grants follow nested DBA_ROLE_PRIVS membership,
*   including roles granted to PUBLIC. System privileges are the ANY privileges
*   that apply to the object's type (SELECT ANY TABLE, EXECUTE ANY PROCEDURE,
*   and so on), both granted directly and inherited through roles. PUBLIC grants
*   apply to every user. The object owner has implicit full privileges even
*   when no grant row exists. Synonyms are reported as named; grants usually
*   live on the underlying object. Press Enter at the SQL*Plus prompt if the
*   optional grantee is omitted.
*
* Parameters:
*   &1 - Required object name in OWNER.OBJECT_NAME format
*   &2 - Optional user or role. If omitted, every grantee is listed
*
* Required Privileges:
*   - SELECT on DBA_OBJECTS
*   - SELECT on DBA_SYNONYMS
*   - SELECT on DBA_TAB_PRIVS
*   - SELECT on DBA_COL_PRIVS
*   - SELECT on DBA_SYS_PRIVS
*   - SELECT on DBA_ROLE_PRIVS
*   - SELECT on DBA_ROLES
*   - SELECT on DBA_USERS
*
* Output Format:
*   - Object identity, status, and synonym target when applicable
*   - Direct object and column grants
*   - Object and column grants inherited through roles
*   - Applicable system privileges granted directly or through roles
*
* Example Usage:
*   @access HR.EMPLOYEES
*   @access HR.EMPLOYEES SCOTT
*   @access SYS.DBA_USERS SYSTEM
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
SET WRAP ON

VARIABLE object_owner    VARCHAR2(128)
VARIABLE object_name     VARCHAR2(128)
VARIABLE grantee_filter  VARCHAR2(128)

DECLARE
    l_target       VARCHAR2(261) := UPPER(TRIM('&1'));
    l_filter       VARCHAR2(128) := NULLIF(UPPER(TRIM('&2')), '');
    l_dot_position PLS_INTEGER;
    l_object_count PLS_INTEGER;
    l_filter_count PLS_INTEGER;
BEGIN
    -- Parse and validate the required OWNER.OBJECT_NAME argument.
    l_dot_position := INSTR(l_target, '.');
    IF l_dot_position <= 1
       OR l_dot_position = LENGTH(l_target)
       OR INSTR(l_target, '.', l_dot_position + 1) > 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Object must be in OWNER.OBJECT_NAME format.'
        );
    END IF;

    :object_owner := SUBSTR(l_target, 1, l_dot_position - 1);
    :object_name  := SUBSTR(l_target, l_dot_position + 1);

    -- This interface intentionally supports ordinary, unquoted identifiers.
    IF NOT REGEXP_LIKE(:object_owner, '^[A-Z][A-Z0-9_$#]*$')
       OR NOT REGEXP_LIKE(:object_name, '^[A-Z][A-Z0-9_$#]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Owner and object must be ordinary Oracle identifiers.'
        );
    END IF;

    SELECT COUNT(*)
    INTO l_object_count
    FROM dba_objects
    WHERE owner = :object_owner
      AND object_name = :object_name
      AND object_type NOT LIKE '%PARTITION%';

    IF l_object_count = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'Object ' || :object_owner || '.' || :object_name || ' was not found.'
        );
    END IF;

    IF l_filter IS NOT NULL THEN
        IF l_filter <> 'PUBLIC'
           AND NOT REGEXP_LIKE(l_filter, '^[A-Z][A-Z0-9_$#]*$') THEN
            RAISE_APPLICATION_ERROR(
                -20004,
                'Grantee must be an ordinary Oracle identifier or PUBLIC.'
            );
        END IF;

        IF l_filter = 'PUBLIC' THEN
            l_filter_count := 1;
        ELSE
            SELECT COUNT(*)
            INTO l_filter_count
            FROM (
                SELECT username AS name FROM dba_users WHERE username = l_filter
                UNION ALL
                SELECT role FROM dba_roles WHERE role = l_filter
            );
        END IF;

        IF l_filter_count = 0 THEN
            RAISE_APPLICATION_ERROR(
                -20005,
                'Grantee ' || l_filter || ' was not found as a user, role, or PUBLIC.'
            );
        END IF;
    END IF;

    :grantee_filter := l_filter;
END;
/

SET FEEDBACK ON

COLUMN owner           FORMAT A20 HEADING 'Owner'
COLUMN object_name     FORMAT A30 HEADING 'Object'
COLUMN object_type     FORMAT A24 HEADING 'Type'
COLUMN object_status   FORMAT A8  HEADING 'Status'
COLUMN created_at      FORMAT A19 HEADING 'Created'
COLUMN last_ddl        FORMAT A19 HEADING 'Last DDL'
COLUMN grantee_filter  FORMAT A30 HEADING 'Grantee Filter'
COLUMN owner_access    FORMAT A80 HEADING 'Owner Access'
COLUMN synonym_target  FORMAT A80 HEADING 'Synonym Target'

PROMPT
PROMPT === Object ===
PROMPT

SELECT
    o.owner,
    o.object_name,
    o.object_type,
    o.status AS object_status,
    TO_CHAR(o.created, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
    TO_CHAR(o.last_ddl_time, 'YYYY-MM-DD HH24:MI:SS') AS last_ddl
FROM dba_objects o
WHERE o.owner = :object_owner
  AND o.object_name = :object_name
  AND o.object_type NOT LIKE '%PARTITION%'
ORDER BY o.object_type;

SELECT NVL(:grantee_filter, '(all grantees)') AS grantee_filter
FROM dual;

SELECT
    :object_owner || ' has implicit full privileges on ' ||
    :object_owner || '.' || :object_name AS owner_access
FROM dual
WHERE :grantee_filter IS NULL
   OR :grantee_filter = :object_owner;

SELECT
    CASE
        WHEN s.synonym_name IS NULL THEN '(not a synonym)'
        WHEN s.db_link IS NOT NULL THEN
            s.table_owner || '.' || s.table_name || '@' || s.db_link ||
            ' (remote; grants below are on the synonym only)'
        ELSE
            s.table_owner || '.' || s.table_name ||
            ' (grants below are on the synonym; check the target object too)'
    END AS synonym_target
FROM dual
LEFT JOIN dba_synonyms s
  ON s.owner = :object_owner
 AND s.synonym_name = :object_name;

COLUMN grantee      FORMAT A30 HEADING 'Grantee'
COLUMN privilege    FORMAT A32 HEADING 'Privilege'
COLUMN column_name  FORMAT A30 HEADING 'Column'
COLUMN grantor      FORMAT A30 HEADING 'Grantor'
COLUMN grantable    FORMAT A9  HEADING 'Grantable'
COLUMN hierarchy    FORMAT A9  HEADING 'Hierarchy'
COLUMN grant_path   FORMAT A80 HEADING 'Path'
COLUMN admin_option FORMAT A5  HEADING 'Admin'

PROMPT
PROMPT === Direct grants ===
PROMPT

SELECT
    p.grantee,
    p.privilege,
    CAST(NULL AS VARCHAR2(128)) AS column_name,
    p.grantor,
    p.grantable,
    p.hierarchy
FROM dba_tab_privs p
WHERE p.owner = :object_owner
  AND p.table_name = :object_name
  AND (
      :grantee_filter IS NULL
      OR p.grantee = :grantee_filter
      OR p.grantee = 'PUBLIC'
  )
UNION ALL
SELECT
    p.grantee,
    p.privilege,
    p.column_name,
    p.grantor,
    p.grantable,
    CAST(NULL AS VARCHAR2(3)) AS hierarchy
FROM dba_col_privs p
WHERE p.owner = :object_owner
  AND p.table_name = :object_name
  AND (
      :grantee_filter IS NULL
      OR p.grantee = :grantee_filter
      OR p.grantee = 'PUBLIC'
  )
ORDER BY grantee, column_name NULLS FIRST, privilege;

PROMPT
PROMPT === Grants via roles ===
PROMPT

WITH role_object_grants AS (
    SELECT
        p.grantee AS granted_role,
        p.privilege,
        CAST(NULL AS VARCHAR2(128)) AS column_name,
        p.grantor,
        p.grantable
    FROM dba_tab_privs p
    JOIN dba_roles r
      ON r.role = p.grantee
    WHERE p.owner = :object_owner
      AND p.table_name = :object_name
    UNION ALL
    SELECT
        p.grantee,
        p.privilege,
        p.column_name,
        p.grantor,
        p.grantable
    FROM dba_col_privs p
    JOIN dba_roles r
      ON r.role = p.grantee
    WHERE p.owner = :object_owner
      AND p.table_name = :object_name
),
role_holders AS (
    SELECT
        CONNECT_BY_ROOT rp.granted_role AS granted_role,
        rp.grantee,
        CONNECT_BY_ROOT rp.granted_role
            || SYS_CONNECT_BY_PATH(rp.grantee, ' -> ') AS grant_path
    FROM dba_role_privs rp
    START WITH rp.granted_role IN (
        SELECT granted_role FROM role_object_grants
    )
    CONNECT BY NOCYCLE PRIOR rp.grantee = rp.granted_role
)
SELECT
    h.grantee,
    g.privilege,
    g.column_name,
    g.grantor,
    g.grantable,
    h.grant_path
FROM role_holders h
JOIN role_object_grants g
  ON g.granted_role = h.granted_role
WHERE :grantee_filter IS NULL
   OR h.grantee = :grantee_filter
   OR h.grantee = 'PUBLIC'
ORDER BY h.grantee, g.column_name NULLS FIRST, g.privilege, h.grant_path;

PROMPT
PROMPT === System privileges ===
PROMPT

WITH priv_map AS (
    SELECT 'TABLE' AS object_type, 'SELECT ANY TABLE' AS privilege FROM dual UNION ALL
    SELECT 'TABLE', 'READ ANY TABLE' FROM dual UNION ALL
    SELECT 'TABLE', 'INSERT ANY TABLE' FROM dual UNION ALL
    SELECT 'TABLE', 'UPDATE ANY TABLE' FROM dual UNION ALL
    SELECT 'TABLE', 'DELETE ANY TABLE' FROM dual UNION ALL
    SELECT 'TABLE', 'ALTER ANY TABLE' FROM dual UNION ALL
    SELECT 'TABLE', 'DROP ANY TABLE' FROM dual UNION ALL
    SELECT 'TABLE', 'LOCK ANY TABLE' FROM dual UNION ALL
    SELECT 'TABLE', 'FLASHBACK ANY TABLE' FROM dual UNION ALL
    SELECT 'TABLE', 'COMMENT ANY TABLE' FROM dual UNION ALL
    SELECT 'TABLE', 'UNDER ANY TABLE' FROM dual UNION ALL
    SELECT 'TABLE', 'BACKUP ANY TABLE' FROM dual UNION ALL
    SELECT 'TABLE', 'ANALYZE ANY' FROM dual UNION ALL
    SELECT 'VIEW', 'SELECT ANY TABLE' FROM dual UNION ALL
    SELECT 'VIEW', 'READ ANY TABLE' FROM dual UNION ALL
    SELECT 'VIEW', 'INSERT ANY TABLE' FROM dual UNION ALL
    SELECT 'VIEW', 'UPDATE ANY TABLE' FROM dual UNION ALL
    SELECT 'VIEW', 'DELETE ANY TABLE' FROM dual UNION ALL
    SELECT 'VIEW', 'DROP ANY VIEW' FROM dual UNION ALL
    SELECT 'VIEW', 'UNDER ANY VIEW' FROM dual UNION ALL
    SELECT 'VIEW', 'FLASHBACK ANY TABLE' FROM dual UNION ALL
    SELECT 'VIEW', 'COMMENT ANY TABLE' FROM dual UNION ALL
    SELECT 'VIEW', 'MERGE ANY VIEW' FROM dual UNION ALL
    SELECT 'MATERIALIZED VIEW', 'SELECT ANY TABLE' FROM dual UNION ALL
    SELECT 'MATERIALIZED VIEW', 'READ ANY TABLE' FROM dual UNION ALL
    SELECT 'MATERIALIZED VIEW', 'INSERT ANY TABLE' FROM dual UNION ALL
    SELECT 'MATERIALIZED VIEW', 'UPDATE ANY TABLE' FROM dual UNION ALL
    SELECT 'MATERIALIZED VIEW', 'DELETE ANY TABLE' FROM dual UNION ALL
    SELECT 'MATERIALIZED VIEW', 'ALTER ANY MATERIALIZED VIEW' FROM dual UNION ALL
    SELECT 'MATERIALIZED VIEW', 'DROP ANY MATERIALIZED VIEW' FROM dual UNION ALL
    SELECT 'MATERIALIZED VIEW', 'FLASHBACK ANY TABLE' FROM dual UNION ALL
    SELECT 'SEQUENCE', 'SELECT ANY SEQUENCE' FROM dual UNION ALL
    SELECT 'SEQUENCE', 'ALTER ANY SEQUENCE' FROM dual UNION ALL
    SELECT 'SEQUENCE', 'DROP ANY SEQUENCE' FROM dual UNION ALL
    SELECT 'PROCEDURE', 'EXECUTE ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'PROCEDURE', 'DEBUG ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'PROCEDURE', 'ALTER ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'PROCEDURE', 'DROP ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'FUNCTION', 'EXECUTE ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'FUNCTION', 'DEBUG ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'FUNCTION', 'ALTER ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'FUNCTION', 'DROP ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'PACKAGE', 'EXECUTE ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'PACKAGE', 'DEBUG ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'PACKAGE', 'ALTER ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'PACKAGE', 'DROP ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'PACKAGE BODY', 'EXECUTE ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'PACKAGE BODY', 'DEBUG ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'PACKAGE BODY', 'ALTER ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'PACKAGE BODY', 'DROP ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'TYPE', 'EXECUTE ANY TYPE' FROM dual UNION ALL
    SELECT 'TYPE', 'UNDER ANY TYPE' FROM dual UNION ALL
    SELECT 'TYPE', 'ALTER ANY TYPE' FROM dual UNION ALL
    SELECT 'TYPE', 'DROP ANY TYPE' FROM dual UNION ALL
    SELECT 'TYPE BODY', 'EXECUTE ANY TYPE' FROM dual UNION ALL
    SELECT 'TYPE BODY', 'ALTER ANY TYPE' FROM dual UNION ALL
    SELECT 'TYPE BODY', 'DROP ANY TYPE' FROM dual UNION ALL
    SELECT 'TRIGGER', 'ALTER ANY TRIGGER' FROM dual UNION ALL
    SELECT 'TRIGGER', 'DROP ANY TRIGGER' FROM dual UNION ALL
    SELECT 'INDEX', 'ALTER ANY INDEX' FROM dual UNION ALL
    SELECT 'INDEX', 'DROP ANY INDEX' FROM dual UNION ALL
    SELECT 'SYNONYM', 'DROP ANY SYNONYM' FROM dual UNION ALL
    SELECT 'SYNONYM', 'DROP ANY PUBLIC SYNONYM' FROM dual UNION ALL
    SELECT 'SYNONYM', 'DROP PUBLIC SYNONYM' FROM dual UNION ALL
    SELECT 'DIRECTORY', 'DROP ANY DIRECTORY' FROM dual UNION ALL
    SELECT 'LIBRARY', 'EXECUTE ANY LIBRARY' FROM dual UNION ALL
    SELECT 'LIBRARY', 'ALTER ANY LIBRARY' FROM dual UNION ALL
    SELECT 'LIBRARY', 'DROP ANY LIBRARY' FROM dual UNION ALL
    SELECT 'OPERATOR', 'EXECUTE ANY OPERATOR' FROM dual UNION ALL
    SELECT 'OPERATOR', 'ALTER ANY OPERATOR' FROM dual UNION ALL
    SELECT 'OPERATOR', 'DROP ANY OPERATOR' FROM dual UNION ALL
    SELECT 'INDEXTYPE', 'EXECUTE ANY INDEXTYPE' FROM dual UNION ALL
    SELECT 'INDEXTYPE', 'ALTER ANY INDEXTYPE' FROM dual UNION ALL
    SELECT 'INDEXTYPE', 'DROP ANY INDEXTYPE' FROM dual UNION ALL
    SELECT 'JAVA CLASS', 'EXECUTE ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'JAVA SOURCE', 'EXECUTE ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'JAVA RESOURCE', 'EXECUTE ANY PROCEDURE' FROM dual UNION ALL
    SELECT 'QUEUE', 'DEQUEUE ANY QUEUE' FROM dual UNION ALL
    SELECT 'QUEUE', 'ENQUEUE ANY QUEUE' FROM dual UNION ALL
    SELECT 'QUEUE', 'MANAGE ANY QUEUE' FROM dual
),
applicable AS (
    SELECT DISTINCT m.privilege
    FROM dba_objects o
    JOIN priv_map m
      ON m.object_type = o.object_type
    WHERE o.owner = :object_owner
      AND o.object_name = :object_name
      AND o.object_type NOT LIKE '%PARTITION%'
      AND NOT (m.privilege IN ('DROP ANY PUBLIC SYNONYM', 'DROP PUBLIC SYNONYM')
               AND o.owner <> 'PUBLIC')
      AND NOT (m.privilege = 'DROP ANY SYNONYM' AND o.owner = 'PUBLIC')
    UNION
    SELECT 'SELECT ANY DICTIONARY'
    FROM dual
    WHERE :object_owner = 'SYS'
),
sys_grants AS (
    SELECT s.grantee, s.privilege, s.admin_option
    FROM dba_sys_privs s
    JOIN applicable a
      ON a.privilege = s.privilege
),
direct_sys AS (
    SELECT
        s.grantee,
        s.privilege,
        s.admin_option,
        'DIRECT' AS grant_path,
        1 AS path_kind
    FROM sys_grants s
    WHERE s.grantee = 'PUBLIC'
       OR EXISTS (
              SELECT 1
              FROM dba_users u
              WHERE u.username = s.grantee
          )
),
role_holders AS (
    SELECT
        CONNECT_BY_ROOT rp.granted_role AS granted_role,
        rp.grantee,
        CONNECT_BY_ROOT rp.granted_role
            || SYS_CONNECT_BY_PATH(rp.grantee, ' -> ') AS grant_path
    FROM dba_role_privs rp
    START WITH rp.granted_role IN (
        SELECT g.grantee
        FROM sys_grants g
        JOIN dba_roles r
          ON r.role = g.grantee
    )
    CONNECT BY NOCYCLE PRIOR rp.grantee = rp.granted_role
),
via_role_sys AS (
    SELECT
        h.grantee,
        s.privilege,
        s.admin_option,
        h.grant_path,
        2 AS path_kind
    FROM role_holders h
    JOIN sys_grants s
      ON s.grantee = h.granted_role
)
SELECT grantee, privilege, grant_path, admin_option
FROM (
    SELECT grantee, privilege, admin_option, grant_path, path_kind
    FROM direct_sys
    UNION ALL
    SELECT grantee, privilege, admin_option, grant_path, path_kind
    FROM via_role_sys
)
WHERE :grantee_filter IS NULL
   OR grantee = :grantee_filter
   OR grantee = 'PUBLIC'
ORDER BY path_kind, grantee, privilege, grant_path;
