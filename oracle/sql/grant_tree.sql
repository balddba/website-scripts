/*******************************************************************************
*
* Script Name: grant_tree.sql
* Title: Grant hierarchy tree
* Tags: Security, Grants, Roles, Privileges
* Purpose: Display the nested grant hierarchy for an Oracle user or role as a tree
*
* Description:
*   Walks DBA_ROLE_PRIVS from a user or role and prints an ASCII tree of
*   nested roles. System, object, and column privileges granted at each
*   level appear as leaves. Circular role grants are shown once and not
*   expanded again on that path. Grants to PUBLIC are omitted unless the
*   starting name is PUBLIC; they apply to every user and would drown the
*   tree. Press Enter at the SQL*Plus prompt if the optional mode is omitted.
*
* Parameters:
*   &1 - Required user, role, or PUBLIC
*   &2 - Optional mode: ALL (default), SYS, or ROLES
*        ALL   - nested roles plus system, object, and column privileges
*        SYS   - nested roles plus system privileges
*        ROLES - nested roles only
*
* Required Privileges:
*   - SELECT on DBA_USERS
*   - SELECT on DBA_ROLES
*   - SELECT on DBA_ROLE_PRIVS
*   - SELECT on DBA_SYS_PRIVS
*   - SELECT on DBA_TAB_PRIVS
*   - SELECT on DBA_COL_PRIVS
*
* Output Format:
*   - Grantee identity and type
*   - ASCII tree of nested grants
*   - Type, admin/default/grantable options, and object grantor
*
* Example Usage:
*   @grant_tree SCOTT
*   @grant_tree SCOTT ROLES
*   @grant_tree APP_READ SYS
*   @grant_tree DBA ROLES
*   @grant_tree PUBLIC ROLES
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 260
SET PAGESIZE 5000
SET TRIMSPOOL ON
SET TAB OFF
SET WRAP OFF
SET NULL ''

VARIABLE grantee      VARCHAR2(128)
VARIABLE grantee_kind VARCHAR2(10)
VARIABLE report_mode  VARCHAR2(10)

DECLARE
    l_grantee      VARCHAR2(128) := UPPER(TRIM('&1'));
    l_mode         VARCHAR2(10)  := NVL(UPPER(TRIM('&2')), 'ALL');
    l_kind         VARCHAR2(10);
BEGIN
    IF l_grantee IS NULL THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'User or role name is required.'
        );
    END IF;

    IF l_grantee <> 'PUBLIC'
       AND NOT REGEXP_LIKE(l_grantee, '^[A-Z][A-Z0-9_$#]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Name must be an ordinary Oracle identifier or PUBLIC.'
        );
    END IF;

    IF l_mode NOT IN ('ALL', 'SYS', 'ROLES') THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'Mode must be ALL, SYS, or ROLES.'
        );
    END IF;

    SELECT MAX(kind)
    INTO l_kind
    FROM (
        SELECT 'USER' AS kind
        FROM dba_users
        WHERE username = l_grantee
        UNION ALL
        SELECT 'ROLE'
        FROM dba_roles
        WHERE role = l_grantee
        UNION ALL
        SELECT 'PUBLIC'
        FROM dual
        WHERE l_grantee = 'PUBLIC'
    );

    IF l_kind IS NULL THEN
        RAISE_APPLICATION_ERROR(
            -20004,
            l_grantee || ' was not found as a user, role, or PUBLIC.'
        );
    END IF;

    :grantee      := l_grantee;
    :grantee_kind := l_kind;
    :report_mode  := l_mode;
END;
/

COLUMN grantee       FORMAT A30  HEADING 'Grantee'
COLUMN grantee_kind  FORMAT A10  HEADING 'Type'
COLUMN report_mode   FORMAT A10  HEADING 'Mode'
COLUMN account_status FORMAT A18 HEADING 'Status'
COLUMN grant_tree    FORMAT A140 HEADING 'Grant Tree'
COLUMN node_type     FORMAT A8   HEADING 'Type'
COLUMN options       FORMAT A28  HEADING 'Options'
COLUMN grantor       FORMAT A30  HEADING 'Grantor'

PROMPT
PROMPT === Grantee ===
PROMPT

SELECT
    :grantee AS grantee,
    :grantee_kind AS grantee_kind,
    :report_mode AS report_mode,
    u.account_status
FROM dual
LEFT JOIN dba_users u
    ON u.username = :grantee;

PROMPT
PROMPT === Grant tree ===
PROMPT

WITH role_nodes AS (
    SELECT CAST(:grantee AS VARCHAR2(128)) AS node_name
    FROM dual
    UNION
    SELECT rp.granted_role
    FROM dba_role_privs rp
    START WITH rp.grantee = :grantee
    CONNECT BY NOCYCLE PRIOR rp.granted_role = rp.grantee
),
edges AS (
    SELECT
        rp.grantee AS parent_name,
        CAST(rp.granted_role AS VARCHAR2(512)) AS child_name,
        CAST('ROLE' AS VARCHAR2(8)) AS child_type,
        CAST(
            'default=' || rp.default_role || ' admin=' || rp.admin_option
            AS VARCHAR2(40)
        ) AS options,
        CAST(NULL AS VARCHAR2(128)) AS grantor,
        CAST(rp.granted_role AS VARCHAR2(512)) AS sort_name
    FROM dba_role_privs rp
    JOIN role_nodes n
      ON n.node_name = rp.grantee
    UNION ALL
    SELECT
        sp.grantee,
        CAST(sp.privilege AS VARCHAR2(512)),
        CAST('SYS' AS VARCHAR2(8)),
        CAST('admin=' || sp.admin_option AS VARCHAR2(40)),
        CAST(NULL AS VARCHAR2(128)),
        CAST(sp.privilege AS VARCHAR2(512))
    FROM dba_sys_privs sp
    JOIN role_nodes n
      ON n.node_name = sp.grantee
    WHERE :report_mode IN ('ALL', 'SYS')
    UNION ALL
    SELECT
        tp.grantee,
        CAST(
            tp.privilege || ' ON ' || tp.owner || '.' || tp.table_name
            AS VARCHAR2(512)
        ),
        CAST('OBJECT' AS VARCHAR2(8)),
        CAST('grantable=' || tp.grantable AS VARCHAR2(40)),
        tp.grantor,
        CAST(
            tp.owner || '.' || tp.table_name || '.' || tp.privilege
            AS VARCHAR2(512)
        )
    FROM dba_tab_privs tp
    JOIN role_nodes n
      ON n.node_name = tp.grantee
    WHERE :report_mode = 'ALL'
    UNION ALL
    SELECT
        cp.grantee,
        CAST(
            cp.privilege || '(' || cp.column_name || ') ON '
                || cp.owner || '.' || cp.table_name
            AS VARCHAR2(512)
        ),
        CAST('COLUMN' AS VARCHAR2(8)),
        CAST('grantable=' || cp.grantable AS VARCHAR2(40)),
        cp.grantor,
        CAST(
            cp.owner || '.' || cp.table_name || '.'
                || cp.column_name || '.' || cp.privilege
            AS VARCHAR2(512)
        )
    FROM dba_col_privs cp
    JOIN role_nodes n
      ON n.node_name = cp.grantee
    WHERE :report_mode = 'ALL'
),
siblings AS (
    SELECT
        e.parent_name,
        e.child_name,
        e.child_type,
        e.options,
        e.grantor,
        ROW_NUMBER() OVER (
            PARTITION BY e.parent_name
            ORDER BY
                CASE e.child_type
                    WHEN 'ROLE' THEN 1
                    WHEN 'SYS' THEN 2
                    WHEN 'OBJECT' THEN 3
                    ELSE 4
                END,
                e.sort_name
        ) AS sibling_n,
        COUNT(*) OVER (PARTITION BY e.parent_name) AS sibling_cnt
    FROM edges e
),
grant_tree (
    node_name,
    node_type,
    options,
    grantor,
    lvl,
    is_last,
    sibling_n,
    prefix,
    seen
) AS (
    SELECT
        CAST(:grantee AS VARCHAR2(512)) AS node_name,
        CAST(:grantee_kind AS VARCHAR2(8)) AS node_type,
        CAST(NULL AS VARCHAR2(40)) AS options,
        CAST(NULL AS VARCHAR2(128)) AS grantor,
        1 AS lvl,
        1 AS is_last,
        1 AS sibling_n,
        CAST('' AS VARCHAR2(4000)) AS prefix,
        CAST('/' || :grantee || '/' AS VARCHAR2(4000)) AS seen
    FROM dual
    UNION ALL
    SELECT
        CAST(s.child_name AS VARCHAR2(512)),
        CAST(
            CASE
                WHEN s.child_type = 'ROLE'
                     AND INSTR(t.seen, '/' || s.child_name || '/') > 0
                THEN 'LOOP'
                ELSE s.child_type
            END AS VARCHAR2(8)
        ),
        s.options,
        s.grantor,
        t.lvl + 1,
        CASE WHEN s.sibling_n = s.sibling_cnt THEN 1 ELSE 0 END,
        s.sibling_n,
        CAST(
            CASE
                WHEN t.lvl = 1 THEN t.prefix
                WHEN t.is_last = 1 THEN t.prefix || '    '
                ELSE t.prefix || '|   '
            END AS VARCHAR2(4000)
        ),
        CAST(t.seen || s.child_name || '/' AS VARCHAR2(4000))
    FROM grant_tree t
    JOIN siblings s
      ON s.parent_name = t.node_name
    WHERE t.node_type IN ('USER', 'ROLE', 'PUBLIC')
      AND t.lvl < 20
)
SEARCH DEPTH FIRST BY sibling_n SET walk_order
SELECT
    t.prefix
        || CASE
               WHEN t.lvl = 1 THEN ''
               WHEN t.is_last = 1 THEN '`-- '
               ELSE '|-- '
           END
        || t.node_name
        || CASE WHEN t.node_type = 'LOOP' THEN ' [cycle]' ELSE '' END
        AS grant_tree,
    t.node_type,
    t.options,
    t.grantor
FROM grant_tree t
ORDER BY t.walk_order;
