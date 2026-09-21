/*******************************************************************************
*
* Script Name: user_expiry_report.sql
* Title: User Password Expiry Report
* Tags: Security, Users, Profiles
* Purpose: Reports user accounts expiring soon, expired/locked status, and profile password limits from dba_users and dba_profiles.
*
* Description:
*   Inspects database user accounts for password expiration and account lock
*   status. Reports accounts that are already expired, locked, or scheduled
*   to expire within a specified number of days (default: 30 days). Also
*   displays profile password policy limits from DBA_PROFILES.
*
* Parameters:
*   &1 - (Optional) Days threshold for expiring-soon accounts (default: 30)
*
* Required Privileges:
*   - SELECT on DBA_USERS
*   - SELECT on DBA_PROFILES
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Account status distribution summary
*   - User accounts expiring soon (within N days)
*   - Expired, locked, or expired/locked user accounts
*   - Profile password policy limits (life time, grace time, failed attempts)
*
* Example Usage:
*   sqlplus user/password@yourdb @user_expiry_report.sql
*   sqlplus user/password@yourdb @user_expiry_report.sql 14
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 200
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN account_status     FORMAT A22             HEADING 'Account Status'
COLUMN user_count         FORMAT 999,990         HEADING 'User Count'
COLUMN username           FORMAT A30             HEADING 'Username'
COLUMN profile            FORMAT A20             HEADING 'Profile'
COLUMN expiry_date        FORMAT A19             HEADING 'Expiry Date'
COLUMN days_left          FORMAT 999,990.0       HEADING 'Days Left'
COLUMN lock_date          FORMAT A19             HEADING 'Lock Date'
COLUMN created            FORMAT A19             HEADING 'Created Date'
COLUMN resource_name      FORMAT A25             HEADING 'Resource Name'
COLUMN limit              FORMAT A20             HEADING 'Limit'

PROMPT
PROMPT ===============================================================================
PROMPT User Password Expiry Report
PROMPT ===============================================================================

PROMPT
PROMPT === Account Status Distribution ===
PROMPT

SELECT
    account_status,
    COUNT(*) AS user_count
FROM dba_users
GROUP BY account_status
ORDER BY user_count DESC, account_status;

PROMPT
PROMPT === Accounts Expiring Soon (Within &1 Days, Default: 30) ===
PROMPT

SELECT
    username,
    account_status,
    profile,
    TO_CHAR(expiry_date, 'YYYY-MM-DD HH24:MI:SS') AS expiry_date,
    ROUND(expiry_date - SYSDATE, 1) AS days_left
FROM dba_users
WHERE expiry_date IS NOT NULL
  AND expiry_date >= SYSDATE
  AND expiry_date <= SYSDATE + TO_NUMBER(NVL('&1', '30'))
ORDER BY expiry_date, username;

PROMPT
PROMPT === Expired and Locked Accounts ===
PROMPT

SELECT
    username,
    account_status,
    profile,
    TO_CHAR(lock_date, 'YYYY-MM-DD HH24:MI:SS') AS lock_date,
    TO_CHAR(expiry_date, 'YYYY-MM-DD HH24:MI:SS') AS expiry_date
FROM dba_users
WHERE account_status NOT LIKE 'OPEN%'
ORDER BY account_status, username;

PROMPT
PROMPT === Profile Password Policy Limits ===
PROMPT

SELECT
    profile,
    resource_name,
    limit
FROM dba_profiles
WHERE resource_name IN (
    'PASSWORD_LIFE_TIME',
    'PASSWORD_GRACE_TIME',
    'PASSWORD_REUSE_TIME',
    'PASSWORD_REUSE_MAX',
    'FAILED_LOGIN_ATTEMPTS',
    'PASSWORD_LOCK_TIME'
)
ORDER BY profile, resource_name;

COLUMN account_status CLEAR
COLUMN user_count CLEAR
COLUMN username CLEAR
COLUMN profile CLEAR
COLUMN expiry_date CLEAR
COLUMN days_left CLEAR
COLUMN lock_date CLEAR
COLUMN created CLEAR
COLUMN resource_name CLEAR
COLUMN limit CLEAR

SET FEEDBACK ON
SET VERIFY ON
