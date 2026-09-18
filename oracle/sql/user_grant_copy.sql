/*******************************************************************************
*
* Script Name: user_grant_copy.sql
* Title: Copy user grants
* Tags: Security, Grants
* Purpose: Synchronize system, role, and object privileges from a source user to a target user
*
* Description:
*   Copies grants from a reference user onto a target user and reports GRANT
*   and REVOKE operations as they run.
*
* Parameters:
*   &1 - (Required) Source user whose privileges are the reference
*   &2 - (Required) Target user to synchronize
*
* Required Privileges:
*   - SELECT on DBA_SYS_PRIVS, DBA_ROLE_PRIVS, DBA_TAB_PRIVS
*   - GRANT ANY PRIVILEGE
*   - GRANT ANY ROLE
*   - GRANT ANY OBJECT PRIVILEGE
*
* Output Format:
*   - Lists privilege changes as GRANT and REVOKE statements execute
*   - Confirms completion of synchronization
*
* Example Usage:
*   SQL> @user_grant_copy ADMIN_USER NEW_USER
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

DECLARE
  v_source_user VARCHAR2(30) := '&user1';
  v_target_user VARCHAR2(30) := '&user2';
  v_sql         VARCHAR2(1000);
  v_found       BOOLEAN;
BEGIN
  -- System Privileges
  DBMS_OUTPUT.PUT_LINE('--- SYSTEM PRIVILEGES ---');
  v_found := FALSE;
  FOR r IN (
    SELECT privilege
    FROM dba_sys_privs
    WHERE grantee = UPPER(v_source_user)
      AND privilege NOT IN (
        SELECT privilege FROM dba_sys_privs WHERE grantee = UPPER(v_target_user)
      )
  ) LOOP
    v_found := TRUE;
    v_sql := 'GRANT ' || r.privilege || ' TO ' || v_target_user;
    DBMS_OUTPUT.PUT_LINE(v_sql);
    EXECUTE IMMEDIATE v_sql;
  END LOOP;
  IF NOT v_found THEN
    DBMS_OUTPUT.PUT_LINE('NONE');
  END IF;

  -- Object Privileges
  DBMS_OUTPUT.PUT_LINE('--- OBJECT PRIVILEGES ---');
  v_found := FALSE;
  FOR r IN (
    SELECT owner, table_name, privilege
    FROM dba_tab_privs
    WHERE grantee = UPPER(v_source_user)
      AND (owner, table_name, privilege) NOT IN (
        SELECT owner, table_name, privilege FROM dba_tab_privs WHERE grantee = UPPER(v_target_user)
      )
  ) LOOP
    v_found := TRUE;
    v_sql := 'GRANT ' || r.privilege || ' ON ' || r.owner || '.' || r.table_name || ' TO ' || v_target_user;
    DBMS_OUTPUT.PUT_LINE(v_sql);
    EXECUTE IMMEDIATE v_sql;
  END LOOP;
  IF NOT v_found THEN
    DBMS_OUTPUT.PUT_LINE('NONE');
  END IF;

  -- Role Grants
  DBMS_OUTPUT.PUT_LINE('--- ROLE GRANTS ---');
  v_found := FALSE;
  FOR r IN (
    SELECT granted_role
    FROM dba_role_privs
    WHERE grantee = UPPER(v_source_user)
      AND granted_role NOT IN (
        SELECT granted_role FROM dba_role_privs WHERE grantee = UPPER(v_target_user)
      )
  ) LOOP
    v_found := TRUE;
    v_sql := 'GRANT ' || r.granted_role || ' TO ' || v_target_user;
    DBMS_OUTPUT.PUT_LINE(v_sql);
    EXECUTE IMMEDIATE v_sql;
  END LOOP;
  IF NOT v_found THEN
    DBMS_OUTPUT.PUT_LINE('NONE');
  END IF;

  DBMS_OUTPUT.PUT_LINE('--- COPY COMPLETE ---');
END;
/