/*******************************************************************************
*
* Script Name: user_details.sql
* Title: User details
* Tags: Security, Users
* Purpose: Generate a detailed report of an Oracle user account
*
* Description:
*   Displays account status, roles, system and object privileges, owned
*   objects, password policy settings, and last login information.
*
* Parameters:
*   &1 - (Required) Oracle username to analyze
*
* Required Privileges:
*   - SELECT on DBA_USERS
*   - SELECT on DBA_ROLE_PRIVS
*   - SELECT on DBA_SYS_PRIVS
*   - SELECT on DBA_TAB_PRIVS
*   - SELECT on DBA_TABLES
*   - SELECT on DBA_PROFILES
*
* Output Format:
*   - Account summary
*   - Role memberships
*   - System privileges
*   - Object privileges
*   - Owned tables
*   - Password profile settings
*
* Example Usage:
*   SQL> @user_details SCOTT
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/
DEFINE username = '&1'

SET SERVEROUTPUT ON
SET VERIFY OFF

DECLARE
  v_username VARCHAR2(30) := '&username';
  v_found BOOLEAN;
BEGIN
  -- Normalize username
  v_username := UPPER(v_username);

  DBMS_OUTPUT.PUT_LINE('===============================');
  DBMS_OUTPUT.PUT_LINE(' Oracle User Account Summary');
  DBMS_OUTPUT.PUT_LINE('===============================');

  -- Basic Info + Last Login [unchanged]

  -- Roles
  DBMS_OUTPUT.PUT_LINE(CHR(10) || '--- ROLES ---');
  v_found := FALSE;
  FOR r IN (
    SELECT granted_role, admin_option
    FROM dba_role_privs
    WHERE grantee = v_username
  ) LOOP
    v_found := TRUE;
    DBMS_OUTPUT.PUT_LINE('Role: ' || r.granted_role || ' (Admin Option: ' || r.admin_option || ')');
  END LOOP;
  IF NOT v_found THEN
    DBMS_OUTPUT.PUT_LINE('NONE');
  END IF;

  -- System Privileges
  DBMS_OUTPUT.PUT_LINE(CHR(10) || '--- SYSTEM PRIVILEGES ---');
  v_found := FALSE;
  FOR r IN (
    SELECT privilege, admin_option
    FROM dba_sys_privs
    WHERE grantee = v_username
  ) LOOP
    v_found := TRUE;
    DBMS_OUTPUT.PUT_LINE('Privilege: ' || r.privilege || ' (Admin Option: ' || r.admin_option || ')');
  END LOOP;
  IF NOT v_found THEN
    DBMS_OUTPUT.PUT_LINE('NONE');
  END IF;

  -- Object Privileges
  DBMS_OUTPUT.PUT_LINE(CHR(10) || '--- OBJECT PRIVILEGES ---');
  v_found := FALSE;
  FOR r IN (
    SELECT owner, table_name, privilege, grantable
    FROM dba_tab_privs
    WHERE grantee = v_username
  ) LOOP
    v_found := TRUE;
    DBMS_OUTPUT.PUT_LINE('Privilege: ' || r.privilege || ' ON ' || r.owner || '.' || r.table_name || ' (Grantable: ' || r.grantable || ')');
  END LOOP;
  IF NOT v_found THEN
    DBMS_OUTPUT.PUT_LINE('NONE');
  END IF;

  -- Tables Owned
  DBMS_OUTPUT.PUT_LINE(CHR(10) || '--- OWNED TABLES ---');
  v_found := FALSE;
  FOR r IN (
    SELECT table_name FROM dba_tables WHERE owner = v_username
  ) LOOP
    v_found := TRUE;
    DBMS_OUTPUT.PUT_LINE('Table: ' || r.table_name);
  END LOOP;
  IF NOT v_found THEN
    DBMS_OUTPUT.PUT_LINE('NONE');
  END IF;

  -- Password Settings [unchanged]

  DBMS_OUTPUT.PUT_LINE(CHR(10) || '--- END OF REPORT ---');
END;
/
