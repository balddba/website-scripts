/*******************************************************************************
*
* Script Name: roles.sql
* Title: Role grants and privileges
* Tags: Security, Roles
* Purpose: Summarize roles and show grants, system privileges, and object privileges for a role
*
* Description:
*   Lists DBA_ROLES (authentication and ORACLE_MAINTAINED). With no
*   argument, that summary is the whole report. When &1 is a role name,
*   also list roles granted to it, users and roles that have it, system
*   privileges, and object privileges from DBA_TAB_PRIVS. Press Enter at
*   the SQL*Plus prompt if the optional role is omitted.
*
* Parameters:
*   &1 - (Optional) Role name. If omitted, every role is listed (summary only)
*
* Required Privileges:
*   - SELECT on DBA_ROLES
*   - SELECT on DBA_ROLE_PRIVS
*   - SELECT on DBA_SYS_PRIVS
*   - SELECT on DBA_TAB_PRIVS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Role name, authentication, oracle_maintained, common
*   - For a named role: granted roles, grantees, sys privs, object privs
*
* Example Usage:
*   SQL> @roles.sql
*   SQL> @roles.sql DBA
*   SQL> @roles.sql RESOURCE
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 220
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN c_role NEW_VALUE p_role NOPRINT
SELECT NVL(CAST(UPPER(TRIM('&1')) AS VARCHAR2(128)), '*ALL*') AS c_role FROM dual;

COLUMN role                  FORMAT A30              HEADING 'Role'
COLUMN authentication_type   FORMAT A16              HEADING 'Auth'
COLUMN oracle_maintained     FORMAT A8               HEADING 'Oracle'
COLUMN common                FORMAT A8               HEADING 'Common'
COLUMN granted_role          FORMAT A30              HEADING 'Granted Role'
COLUMN admin_option          FORMAT A8               HEADING 'Admin'
COLUMN default_role          FORMAT A8               HEADING 'Default'
COLUMN grantee               FORMAT A30              HEADING 'Grantee'
COLUMN privilege             FORMAT A40              HEADING 'Privilege'
COLUMN owner                 FORMAT A30              HEADING 'Owner'
COLUMN table_name            FORMAT A40              HEADING 'Object'
COLUMN grantable             FORMAT A10              HEADING 'Grantable'

PROMPT
PROMPT === Roles ===
PROMPT
PROMPT Filter: &&p_role

SELECT
    role,
    authentication_type,
    oracle_maintained,
    common
FROM dba_roles
WHERE role = DECODE('&&p_role', '*ALL*', role, '&&p_role')
ORDER BY role;

PROMPT
PROMPT === Roles granted to this role ===
PROMPT
PROMPT Shown only when a single role is requested.

SELECT
    granted_role,
    admin_option,
    default_role
FROM dba_role_privs
WHERE '&&p_role' <> '*ALL*'
  AND grantee = '&&p_role'
ORDER BY granted_role;

PROMPT
PROMPT === Users and roles granted this role ===
PROMPT

SELECT
    grantee,
    admin_option,
    default_role
FROM dba_role_privs
WHERE '&&p_role' <> '*ALL*'
  AND granted_role = '&&p_role'
ORDER BY grantee;

PROMPT
PROMPT === System privileges granted to this role ===
PROMPT

SELECT
    privilege,
    admin_option
FROM dba_sys_privs
WHERE '&&p_role' <> '*ALL*'
  AND grantee = '&&p_role'
ORDER BY privilege;

PROMPT
PROMPT === Object privileges granted to this role ===
PROMPT

SELECT
    owner,
    table_name,
    privilege,
    grantable
FROM dba_tab_privs
WHERE '&&p_role' <> '*ALL*'
  AND grantee = '&&p_role'
ORDER BY owner, table_name, privilege;

COLUMN c_role CLEAR
COLUMN role CLEAR
COLUMN authentication_type CLEAR
COLUMN oracle_maintained CLEAR
COLUMN common CLEAR
COLUMN granted_role CLEAR
COLUMN admin_option CLEAR
COLUMN default_role CLEAR
COLUMN grantee CLEAR
COLUMN privilege CLEAR
COLUMN owner CLEAR
COLUMN table_name CLEAR
COLUMN grantable CLEAR

SET FEEDBACK ON
SET VERIFY ON
