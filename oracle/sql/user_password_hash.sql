/*******************************************************************************
*
* Script Name: user_password_hash.sql
* Title: User password hash
* Tags: Security, Users
* Purpose: Display the password verifier and hash type for a user the DBA administers
*
* Description:
*   Reads DBA_USERS.PASSWORD (legacy 10g verifier column) and SYS.USER$.SPARE4
*   (11g/12c verifiers) for one username. Hash type is derived from
*   PASSWORD_VERSIONS and from SPARE4 prefixes (S: = 11g, T: = 12c, H: =
*   HTTP digest). Output is sensitive: treat it like a password file, do
*   not spool to a shared location, and do not mail or commit the result.
*   Authorized use is limited to databases and accounts you administer.
*   This script does not crack, compare, or attack hashes.
*
* Parameters:
*   &1 - (Required) Oracle username
*
* Required Privileges:
*   - SELECT on DBA_USERS
*   - SELECT on SYS.USER$ (SYS or SYSDBA; SPARE4 is not exposed on DBA_USERS)
*
* Output Format:
*   - Username, account status, authentication type
*   - PASSWORD (10g verifier), SPARE4, PASSWORD_VERSIONS
*   - Hash type labels only (10g / 11g / 12c / HTTP digest)
*
* Example Usage:
*   SQL> CONNECT / AS SYSDBA
*   SQL> @user_password_hash.sql SCOTT
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
SET SERVEROUTPUT ON SIZE UNLIMITED

COLUMN c_user NEW_VALUE p_user NOPRINT
SELECT UPPER(TRIM('&1')) AS c_user FROM dual;

BEGIN
    IF TRIM('&&p_user') IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'Username is required.');
    END IF;
END;
/

COLUMN username            FORMAT A30              HEADING 'Username'
COLUMN account_status      FORMAT A20              HEADING 'Status'
COLUMN authentication_type FORMAT A16              HEADING 'Auth'
COLUMN password            FORMAT A32              HEADING 'PASSWORD (10g)'
COLUMN spare4              FORMAT A120             HEADING 'SPARE4'
COLUMN password_versions   FORMAT A20              HEADING 'Versions'
COLUMN hash_type           FORMAT A40              HEADING 'Hash Type'

PROMPT
PROMPT === Password hash (sensitive) ===
PROMPT
PROMPT Hashes identify the account verifier only. Do not share this output.
PROMPT Authorized DBA use on databases you administer. No cracking.
PROMPT User: &&p_user

SELECT
    u.username,
    u.account_status,
    u.authentication_type,
    u.password,
    s.spare4,
    u.password_versions,
    RTRIM(
        CASE WHEN u.password IS NOT NULL THEN '10g ' END ||
        CASE WHEN s.spare4 LIKE '%S:%' THEN '11g ' END ||
        CASE WHEN s.spare4 LIKE '%T:%' THEN '12c ' END ||
        CASE WHEN s.spare4 LIKE '%Y:%' THEN '12cR2+ ' END ||
        CASE WHEN s.spare4 LIKE '%H:%' THEN 'HTTP-digest ' END ||
        CASE
            WHEN u.password IS NULL
             AND s.spare4 IS NULL
            THEN NVL(u.authentication_type, 'none')
        END
    ) AS hash_type
FROM dba_users u
LEFT JOIN sys.user$ s
    ON s.user# = u.user_id
WHERE u.username = '&&p_user';

COLUMN c_user CLEAR
COLUMN username CLEAR
COLUMN account_status CLEAR
COLUMN authentication_type CLEAR
COLUMN password CLEAR
COLUMN spare4 CLEAR
COLUMN password_versions CLEAR
COLUMN hash_type CLEAR

SET FEEDBACK ON
SET VERIFY ON
