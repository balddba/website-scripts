/*******************************************************************************
*
* Script Name: sql_patches_profiles.sql
* Title: SQL Profiles and Patches
* Tags: Performance, SPM, Profiles
* Purpose: Lists active SQL Profiles from dba_sql_profiles and SQL Patches from dba_sql_patches.
*
* Description:
*   Displays registered SQL Profiles (DBA_SQL_PROFILES) and SQL Patches
*   (DBA_SQL_PATCHES) used for query tuning, outline hints, and plan stability.
*   Reports profile and patch names, category, status (ENABLED/DISABLED), type,
*   force matching setting, creation date, modification date, and SQL text.
*
* Parameters:
*   &1 - (Optional) Profile or patch name pattern. Default is '%' (all).
*
* Required Privileges:
*   - SELECT on DBA_SQL_PROFILES
*   - SELECT on DBA_SQL_PATCHES
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - SQL Profiles: name, category, status, type, force matching, created, modified, SQL text
*   - SQL Patches: name, category, status, force matching, created, modified, SQL text
*
* Example Usage:
*   sqlplus user/password@yourdb @sql_patches_profiles.sql
*   sqlplus user/password@yourdb @sql_patches_profiles.sql SYS_SQLPROF_%
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

COLUMN c_filter NEW_VALUE p_filter NOPRINT
SELECT NVL(NULLIF(TRIM('&1'), ''), '%') AS c_filter FROM dual;

COLUMN name           FORMAT A30              HEADING 'Name'
COLUMN category       FORMAT A15              HEADING 'Category'
COLUMN status         FORMAT A10              HEADING 'Status'
COLUMN type           FORMAT A10              HEADING 'Type'
COLUMN force_matching FORMAT A8               HEADING 'Force'
COLUMN created_time   FORMAT A16              HEADING 'Created'
COLUMN modified_time  FORMAT A16              HEADING 'Modified'
COLUMN sql_text       FORMAT A60 TRUNC        HEADING 'SQL Text'

PROMPT
PROMPT === SQL Profiles (DBA_SQL_PROFILES) ===
PROMPT

SELECT
    name,
    category,
    status,
    type,
    force_matching,
    TO_CHAR(created, 'YYYY-MM-DD HH24:MI') AS created_time,
    TO_CHAR(last_modified, 'YYYY-MM-DD HH24:MI') AS modified_time,
    SUBSTR(sql_text, 1, 60) AS sql_text
FROM dba_sql_profiles
WHERE (name LIKE UPPER('&&p_filter')
   OR UPPER(sql_text) LIKE '%' || UPPER('&&p_filter') || '%')
ORDER BY created DESC, name;

PROMPT
PROMPT === SQL Patches (DBA_SQL_PATCHES) ===
PROMPT

SELECT
    name,
    category,
    status,
    force_matching,
    TO_CHAR(created, 'YYYY-MM-DD HH24:MI') AS created_time,
    TO_CHAR(last_modified, 'YYYY-MM-DD HH24:MI') AS modified_time,
    SUBSTR(sql_text, 1, 60) AS sql_text
FROM dba_sql_patches
WHERE (name LIKE UPPER('&&p_filter')
   OR UPPER(sql_text) LIKE '%' || UPPER('&&p_filter') || '%')
ORDER BY created DESC, name;

COLUMN name CLEAR
COLUMN category CLEAR
COLUMN status CLEAR
COLUMN type CLEAR
COLUMN force_matching CLEAR
COLUMN created_time CLEAR
COLUMN modified_time CLEAR
COLUMN sql_text CLEAR
COLUMN c_filter CLEAR

UNDEFINE p_filter
UNDEFINE 1

SET FEEDBACK ON
SET VERIFY ON
