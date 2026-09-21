/*******************************************************************************
*
* Script Name: whoami.sql
* Title: Connected session identity
* Tags: Sessions
* Purpose: Show the connected user and basic attributes of the current session
*
* Description:
*   Prints a name/value report for the SQL*Plus session: Oracle user and UID,
*   SID, serial number, instance, database and container names, host, OS user,
*   program, logon time, SYSDATE, ISDBA, and current schema. Values come from
*   USERENV and the matching V$SESSION row.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$SESSION
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - One name/value pair per row
*
* Example Usage:
*   SQL> @whoami.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 160
SET PAGESIZE 50
SET TRIMSPOOL ON
SET TAB OFF

COLUMN name  FORMAT A22 HEADING 'Name'
COLUMN value FORMAT A80 HEADING 'Value'

PROMPT
PROMPT === Who am I ===
PROMPT

WITH me AS (
    SELECT
        s.sid,
        s.serial#,
        s.username,
        s.osuser,
        s.program,
        s.logon_time,
        USER AS oracle_user,
        UID AS user_id,
        SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name,
        SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
        SYS_CONTEXT('USERENV', 'DB_UNIQUE_NAME') AS db_unique_name,
        SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
        SYS_CONTEXT('USERENV', 'CON_ID') AS con_id,
        SYS_CONTEXT('USERENV', 'HOST') AS host,
        SYS_CONTEXT('USERENV', 'ISDBA') AS is_dba,
        SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
        SYSDATE AS now
    FROM v$session s
    WHERE s.sid = SYS_CONTEXT('USERENV', 'SID')
)
SELECT name, value
FROM (
    SELECT 1 AS ord, 'User' AS name, oracle_user AS value FROM me
    UNION ALL
    SELECT 2, 'UID', TO_CHAR(user_id) FROM me
    UNION ALL
    SELECT 3, 'SID', TO_CHAR(sid) FROM me
    UNION ALL
    SELECT 4, 'Serial#', TO_CHAR(serial#) FROM me
    UNION ALL
    SELECT 5, 'Instance', instance_name FROM me
    UNION ALL
    SELECT 6, 'DB name', db_name FROM me
    UNION ALL
    SELECT 7, 'DB unique name', db_unique_name FROM me
    UNION ALL
    SELECT 8, 'Container', con_name FROM me
    UNION ALL
    SELECT 9, 'Con ID', con_id FROM me
    UNION ALL
    SELECT 10, 'Host', host FROM me
    UNION ALL
    SELECT 11, 'OS user', osuser FROM me
    UNION ALL
    SELECT 12, 'Program', program FROM me
    UNION ALL
    SELECT 13, 'Logon time', TO_CHAR(logon_time, 'YYYY-MM-DD HH24:MI:SS') FROM me
    UNION ALL
    SELECT 14, 'SYSDATE', TO_CHAR(now, 'YYYY-MM-DD HH24:MI:SS') FROM me
    UNION ALL
    SELECT 15, 'Is DBA', is_dba FROM me
    UNION ALL
    SELECT 16, 'Current schema', current_schema FROM me
)
ORDER BY ord;

COLUMN name CLEAR
COLUMN value CLEAR

SET FEEDBACK ON
SET VERIFY ON
