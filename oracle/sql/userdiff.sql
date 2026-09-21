/*******************************************************************************
*
* Script Name: userdiff.sql
* Title: User privilege diff
* Tags: Security, Grants
* Purpose: Compare database privileges between two Oracle users/schemas
*
* Description:
*   Reports differences in system privileges, role grants, and object
*   privileges between two users.
*
* Parameters:
*   &1 - (Required) First username to compare
*   &2 - (Required) Second username to compare
*
* Required Privileges:
*   - SELECT on DBA_SYS_PRIVS
*   - SELECT on DBA_ROLE_PRIVS
*   - SELECT on DBA_TAB_PRIVS
*
* Output Format:
*   - Detailed comparison of privileges between the two users
*   - Differences highlighted in each privilege category
*
* Example Usage:
*   SQL> @userdiff.sql USER1 USER2
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/
-- Accept input arguments as substitution variables
DEFINE user1 = '&1'
DEFINE user2 = '&2'
 
SET SERVEROUTPUT ON
SET VERIFY OFF
 
DECLARE
    v_user1 VARCHAR2(30) := UPPER('&user1');
    v_user2 VARCHAR2(30) := UPPER('&user2');
    v_diff_found     BOOLEAN := FALSE;
    v_sys_diff       BOOLEAN := FALSE;
    v_role_diff      BOOLEAN := FALSE;
    v_obj_diff       BOOLEAN := FALSE;
    v_quota_diff     BOOLEAN := FALSE;
BEGIN
    DBMS_OUTPUT.PUT_LINE('===========================================');
    DBMS_OUTPUT.PUT_LINE('Comparing privileges between:');
    DBMS_OUTPUT.PUT_LINE('User 1: ' || v_user1);
    DBMS_OUTPUT.PUT_LINE('User 2: ' || v_user2);
    DBMS_OUTPUT.PUT_LINE('===========================================');

    DBMS_OUTPUT.PUT_LINE('--- SYSTEM PRIVILEGES DIFFERENCES ---');

    FOR rec IN (
        SELECT privilege FROM DBA_SYS_PRIVS WHERE grantee = v_user1
        MINUS
        SELECT privilege FROM DBA_SYS_PRIVS WHERE grantee = v_user2
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(v_user1 || ' has but ' || v_user2 || ' does not: ' || rec.privilege);
        v_sys_diff := TRUE;
        v_diff_found := TRUE;
    END LOOP;

    FOR rec IN (
        SELECT privilege FROM DBA_SYS_PRIVS WHERE grantee = v_user2
        MINUS
        SELECT privilege FROM DBA_SYS_PRIVS WHERE grantee = v_user1
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(v_user2 || ' has but ' || v_user1 || ' does not: ' || rec.privilege);
        v_sys_diff := TRUE;
        v_diff_found := TRUE;
    END LOOP;

    IF NOT v_sys_diff THEN
        DBMS_OUTPUT.PUT_LINE('NONE');
    END IF;

    DBMS_OUTPUT.PUT_LINE('--- ROLE GRANTS DIFFERENCES ---');

    FOR rec IN (
        SELECT granted_role FROM DBA_ROLE_PRIVS WHERE grantee = v_user1
        MINUS
        SELECT granted_role FROM DBA_ROLE_PRIVS WHERE grantee = v_user2
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(v_user1 || ' has role but ' || v_user2 || ' does not: ' || rec.granted_role);
        v_role_diff := TRUE;
        v_diff_found := TRUE;
    END LOOP;

    FOR rec IN (
        SELECT granted_role FROM DBA_ROLE_PRIVS WHERE grantee = v_user2
        MINUS
        SELECT granted_role FROM DBA_ROLE_PRIVS WHERE grantee = v_user1
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(v_user2 || ' has role but ' || v_user1 || ' does not: ' || rec.granted_role);
        v_role_diff := TRUE;
        v_diff_found := TRUE;
    END LOOP;

    IF NOT v_role_diff THEN
        DBMS_OUTPUT.PUT_LINE('NONE');
    END IF;

    DBMS_OUTPUT.PUT_LINE('--- OBJECT PRIVILEGES DIFFERENCES ---');

    FOR rec IN (
        SELECT owner, table_name, privilege FROM DBA_TAB_PRIVS
        WHERE grantee = v_user1
        MINUS
        SELECT owner, table_name, privilege FROM DBA_TAB_PRIVS
        WHERE grantee = v_user2
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(v_user1 || ' has on ' || rec.owner || '.' || rec.table_name || ': ' || rec.privilege);
        v_obj_diff := TRUE;
        v_diff_found := TRUE;
    END LOOP;

    FOR rec IN (
        SELECT owner, table_name, privilege FROM DBA_TAB_PRIVS
        WHERE grantee = v_user2
        MINUS
        SELECT owner, table_name, privilege FROM DBA_TAB_PRIVS
        WHERE grantee = v_user1
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(v_user2 || ' has on ' || rec.owner || '.' || rec.table_name || ': ' || rec.privilege);
        v_obj_diff := TRUE;
        v_diff_found := TRUE;
    END LOOP;

    IF NOT v_obj_diff THEN
        DBMS_OUTPUT.PUT_LINE('NONE');
    END IF;

    IF NOT v_diff_found THEN
        DBMS_OUTPUT.PUT_LINE('✅ Users ' || v_user1 || ' and ' || v_user2 || ' have identical privileges.');
    END IF;

    DBMS_OUTPUT.PUT_LINE('--- TABLESPACE QUOTA DIFFERENCES ---');

    FOR rec IN (
        SELECT tablespace_name,
               DECODE(max_bytes, -1, 'UNLIMITED',
                     TO_CHAR(max_bytes/1024/1024) || 'M') as quota
        FROM dba_ts_quotas
        WHERE username = v_user1
        MINUS
        SELECT tablespace_name,
               DECODE(max_bytes, -1, 'UNLIMITED',
                     TO_CHAR(max_bytes/1024/1024) || 'M')
        FROM dba_ts_quotas
        WHERE username = v_user2
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(v_user1 || ' has quota on ' || rec.tablespace_name || ': ' || rec.quota);
        v_quota_diff := TRUE;
        v_diff_found := TRUE;
    END LOOP;

    FOR rec IN (
        SELECT tablespace_name,
               DECODE(max_bytes, -1, 'UNLIMITED',
                     TO_CHAR(max_bytes/1024/1024) || 'M') as quota
        FROM dba_ts_quotas
        WHERE username = v_user2
        MINUS
        SELECT tablespace_name,
               DECODE(max_bytes, -1, 'UNLIMITED',
                     TO_CHAR(max_bytes/1024/1024) || 'M')
        FROM dba_ts_quotas
        WHERE username = v_user1
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(v_user2 || ' has quota on ' || rec.tablespace_name || ': ' || rec.quota);
        v_quota_diff := TRUE;
        v_diff_found := TRUE;
    END LOOP;

    IF NOT v_quota_diff THEN
        DBMS_OUTPUT.PUT_LINE('NONE');
    END IF;

END;
/

UNDEFINE user1
UNDEFINE user2
