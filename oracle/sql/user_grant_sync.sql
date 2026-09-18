/*******************************************************************************
*
* Script Name: user_grant_sync.sql
* Title: Sync user grants
* Tags: Security, Grants
* Purpose: Synchronize privileges, roles, and tablespace quotas between two Oracle users
*
* Description:
*   Grants missing permissions to the target user and revokes extras so both
*   users have matching system privileges, object privileges, roles, and
*   tablespace quotas.
*
* Parameters:
*   &1 - (Required) Source user (template for permissions)
*   &2 - (Required) Target user to synchronize
*
* Required Privileges:
*   - DBA role or equivalent
*   - SELECT on DBA_SYS_PRIVS
*   - SELECT on DBA_TAB_PRIVS
*   - SELECT on DBA_ROLE_PRIVS
*   - SELECT on DBA_TS_QUOTAS
*
* Output Format:
*   - Execution log of GRANT and REVOKE operations by category
*
* Example Usage:
*   SQL> @user_grant_sync.sql TEMPLATE_USER NEW_USER
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
  -- === SYSTEM PRIVILEGES ===
  DBMS_OUTPUT.PUT_LINE('--- SYNC SYSTEM PRIVILEGES ---');
  v_found := FALSE;

  -- Grant missing system privileges
  FOR r IN (
    SELECT privilege
    FROM dba_sys_privs
    WHERE grantee = UPPER(v_source_user)
    MINUS
    SELECT privilege
    FROM dba_sys_privs
    WHERE grantee = UPPER(v_target_user)
  ) LOOP
    v_found := TRUE;
    v_sql := 'GRANT ' || r.privilege || ' TO ' || v_target_user;
    DBMS_OUTPUT.PUT_LINE(v_sql);
    EXECUTE IMMEDIATE v_sql;
  END LOOP;

  -- Revoke extra system privileges
  FOR r IN (
    SELECT privilege
    FROM dba_sys_privs
    WHERE grantee = UPPER(v_target_user)
    MINUS
    SELECT privilege
    FROM dba_sys_privs
    WHERE grantee = UPPER(v_source_user)
  ) LOOP
    v_found := TRUE;
    v_sql := 'REVOKE ' || r.privilege || ' FROM ' || v_target_user;
    DBMS_OUTPUT.PUT_LINE(v_sql);
    EXECUTE IMMEDIATE v_sql;
  END LOOP;
  
  IF NOT v_found THEN
    DBMS_OUTPUT.PUT_LINE('NONE');
  END IF;

  -- === OBJECT PRIVILEGES ===
  DBMS_OUTPUT.PUT_LINE('--- SYNC OBJECT PRIVILEGES ---');
  v_found := FALSE;

  -- Grant missing object privileges
  FOR r IN (
    SELECT owner, table_name, privilege
    FROM dba_tab_privs
    WHERE grantee = UPPER(v_source_user)
    MINUS
    SELECT owner, table_name, privilege
    FROM dba_tab_privs
    WHERE grantee = UPPER(v_target_user)
  ) LOOP
    v_found := TRUE;
    v_sql := 'GRANT ' || r.privilege || ' ON ' || r.owner || '.' || r.table_name || ' TO ' || v_target_user;
    DBMS_OUTPUT.PUT_LINE(v_sql);
    EXECUTE IMMEDIATE v_sql;
  END LOOP;

  -- Revoke extra object privileges
  FOR r IN (
    SELECT owner, table_name, privilege
    FROM dba_tab_privs
    WHERE grantee = UPPER(v_target_user)
    MINUS
    SELECT owner, table_name, privilege
    FROM dba_tab_privs
    WHERE grantee = UPPER(v_source_user)
  ) LOOP
    v_found := TRUE;
    v_sql := 'REVOKE ' || r.privilege || ' ON ' || r.owner || '.' || r.table_name || ' FROM ' || v_target_user;
    DBMS_OUTPUT.PUT_LINE(v_sql);
    EXECUTE IMMEDIATE v_sql;
  END LOOP;

  IF NOT v_found THEN
    DBMS_OUTPUT.PUT_LINE('NONE');
  END IF;

  -- === ROLES ===
  DBMS_OUTPUT.PUT_LINE('--- SYNC ROLES ---');
  v_found := FALSE;

  -- Grant missing roles
  FOR r IN (
    SELECT granted_role
    FROM dba_role_privs
    WHERE grantee = UPPER(v_source_user)
    MINUS
    SELECT granted_role
    FROM dba_role_privs
    WHERE grantee = UPPER(v_target_user)
  ) LOOP
    v_found := TRUE;
    v_sql := 'GRANT ' || r.granted_role || ' TO ' || v_target_user;
    DBMS_OUTPUT.PUT_LINE(v_sql);
    EXECUTE IMMEDIATE v_sql;
  END LOOP;

  -- Revoke extra roles
  FOR r IN (
    SELECT granted_role
    FROM dba_role_privs
    WHERE grantee = UPPER(v_target_user)
    MINUS
    SELECT granted_role
    FROM dba_role_privs
    WHERE grantee = UPPER(v_source_user)
  ) LOOP
    v_found := TRUE;
    v_sql := 'REVOKE ' || r.granted_role || ' FROM ' || v_target_user;
    DBMS_OUTPUT.PUT_LINE(v_sql);
    EXECUTE IMMEDIATE v_sql;
  END LOOP;

  IF NOT v_found THEN
    DBMS_OUTPUT.PUT_LINE('NONE');
  END IF;

  -- === TABLESPACE QUOTAS ===
  DBMS_OUTPUT.PUT_LINE('--- SYNC TABLESPACE QUOTAS ---');
  v_found := FALSE;

  -- Set matching quotas
  FOR r IN (
    SELECT tablespace_name, 
           DECODE(max_bytes, -1, 'UNLIMITED', 
                 TO_CHAR(max_bytes)) as quota_bytes
    FROM dba_ts_quotas
    WHERE username = UPPER(v_source_user)
    MINUS
    SELECT tablespace_name, 
           DECODE(max_bytes, -1, 'UNLIMITED',
                 TO_CHAR(max_bytes))
    FROM dba_ts_quotas
    WHERE username = UPPER(v_target_user)
  ) LOOP
    v_found := TRUE;
    IF r.quota_bytes = 'UNLIMITED' THEN
      v_sql := 'ALTER USER ' || v_target_user || ' QUOTA UNLIMITED ON ' || r.tablespace_name;
    ELSE
      v_sql := 'ALTER USER ' || v_target_user || ' QUOTA ' || r.quota_bytes || ' ON ' || r.tablespace_name;
    END IF;
    DBMS_OUTPUT.PUT_LINE(v_sql);
    EXECUTE IMMEDIATE v_sql;
  END LOOP;

  -- Revoke extra quotas
  FOR r IN (
    SELECT tablespace_name
    FROM dba_ts_quotas
    WHERE username = UPPER(v_target_user)
    MINUS
    SELECT tablespace_name
    FROM dba_ts_quotas
    WHERE username = UPPER(v_source_user)
  ) LOOP
    v_found := TRUE;
    v_sql := 'ALTER USER ' || v_target_user || ' QUOTA 0 ON ' || r.tablespace_name;
    DBMS_OUTPUT.PUT_LINE(v_sql);
    EXECUTE IMMEDIATE v_sql;
  END LOOP;

  IF NOT v_found THEN
    DBMS_OUTPUT.PUT_LINE('NONE');
  END IF;

  DBMS_OUTPUT.PUT_LINE('--- SYNC COMPLETE ---');
END;
/