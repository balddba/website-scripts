/*******************************************************************************
*
* Script Name: profiles.sql
* Title: Profile resource and password limits
* Tags: Security, Profiles
* Purpose: Show DBA_PROFILES limits and the users assigned to each profile
*
* Description:
*   Lists resource and password limits from DBA_PROFILES, then the users
*   whose DBA_USERS.PROFILE matches. Press Enter at the SQL*Plus prompt
*   if the optional profile name is omitted. DEFAULT is a real profile;
*   users inherit it when no other profile is assigned.
*
* Parameters:
*   &1 - (Optional) Profile name. If omitted, every profile is listed
*
* Required Privileges:
*   - SELECT on DBA_PROFILES
*   - SELECT on DBA_USERS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Profile, resource name, type (KERNEL/PASSWORD), and limit
*   - Users assigned to each selected profile
*
* Example Usage:
*   SQL> @profiles.sql
*   SQL> @profiles.sql DEFAULT
*   SQL> @profiles.sql MONITORING
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 180
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN profile            FORMAT A30              HEADING 'Profile'
COLUMN resource_name      FORMAT A32              HEADING 'Resource'
COLUMN resource_type      FORMAT A10              HEADING 'Type'
COLUMN limit              FORMAT A40              HEADING 'Limit'
COLUMN username           FORMAT A30              HEADING 'Username'
COLUMN account_status     FORMAT A20              HEADING 'Status'
COLUMN user_profile       FORMAT A30              HEADING 'Profile'

PROMPT
PROMPT === Profile limits ===
PROMPT

SELECT
    profile,
    resource_name,
    resource_type,
    limit
FROM dba_profiles
WHERE CAST(profile AS VARCHAR2(128)) = NVL(
    CAST(UPPER(TRIM('&1')) AS VARCHAR2(128)),
    CAST(profile AS VARCHAR2(128))
)
ORDER BY
    profile,
    resource_type,
    resource_name;

PROMPT
PROMPT === Users assigned to profile ===
PROMPT

SELECT
    profile AS user_profile,
    username,
    account_status
FROM dba_users
WHERE CAST(profile AS VARCHAR2(128)) = NVL(
    CAST(UPPER(TRIM('&1')) AS VARCHAR2(128)),
    CAST(profile AS VARCHAR2(128))
)
ORDER BY profile, username;

COLUMN profile CLEAR
COLUMN resource_name CLEAR
COLUMN resource_type CLEAR
COLUMN limit CLEAR
COLUMN username CLEAR
COLUMN account_status CLEAR
COLUMN user_profile CLEAR

SET FEEDBACK ON
SET VERIFY ON
