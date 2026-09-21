/*******************************************************************************
*
* Script Name: block_change_tracking.sql
* Title: Block change tracking
* Tags: Backup, RMAN, Maintenance
* Purpose: Show block change tracking status and optionally enable it
*
* Description:
*   Reports V$BLOCK_CHANGE_TRACKING (status, filename, bytes). By default
*   the script is status-only. Pass ENABLE as &1 to run ALTER DATABASE
*   ENABLE BLOCK CHANGE TRACKING. Pass a file path as &2 to add USING FILE;
*   omit &2 to let Oracle create an OMF file (typically in the FRA). Does
*   not enable unless &1 is ENABLE. On a CDB, run this from CDB$ROOT.
*   Press Enter at the SQL*Plus prompts for status-only.
*
* Parameters:
*   &1 - (Optional) STATUS (default) or ENABLE
*   &2 - (Optional) Tracking file path when enabling (OMF/FRA if omitted)
*
* Required Privileges:
*   - SELECT on V$BLOCK_CHANGE_TRACKING
*   - ALTER DATABASE to enable block change tracking
*
* Output Format:
*   - Status, filename, and size in bytes
*   - ENABLE statement when requested, then status again
*
* Example Usage:
*   SQL> @block_change_tracking.sql
*   SQL> @block_change_tracking.sql ENABLE
*   SQL> @block_change_tracking.sql ENABLE +DATA/ORCL/changetracking.f
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
SET SERVEROUTPUT ON SIZE UNLIMITED

COLUMN c_action NEW_VALUE p_action NOPRINT
COLUMN c_file   NEW_VALUE p_file   NOPRINT
SELECT
    NVL(CAST(UPPER(TRIM('&1')) AS VARCHAR2(128)), 'STATUS') AS c_action,
    NVL(TRIM('&2'), '') AS c_file
FROM dual;

COLUMN status      FORMAT A12              HEADING 'Status'
COLUMN filename    FORMAT A80              HEADING 'Filename'
COLUMN bytes       FORMAT 999,999,999,990  HEADING 'Bytes'
COLUMN size_mb     FORMAT 999,999,990.0    HEADING 'MB'

PROMPT
PROMPT === Block change tracking ===
PROMPT

SELECT
    status,
    filename,
    bytes,
    ROUND(bytes / 1024 / 1024, 1) AS size_mb
FROM v$block_change_tracking;

PROMPT
PROMPT Action: &&p_action
PROMPT

DECLARE
    l_action VARCHAR2(30) := UPPER(TRIM('&&p_action'));
    l_file   VARCHAR2(4000) := TRIM('&&p_file');
    l_sql    VARCHAR2(4000);
BEGIN
    IF l_action IS NULL OR l_action = 'STATUS' THEN
        DBMS_OUTPUT.PUT_LINE('Status only. Pass ENABLE to turn on block change tracking.');
        RETURN;
    END IF;

    IF l_action <> 'ENABLE' THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Action must be STATUS or ENABLE.'
        );
    END IF;

    IF INSTR(l_file, '''') > 0 THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Tracking file path must not contain a single quote.'
        );
    END IF;

    IF l_file IS NOT NULL THEN
        l_sql := 'ALTER DATABASE ENABLE BLOCK CHANGE TRACKING USING FILE ''' ||
                 l_file || '''';
    ELSE
        l_sql := 'ALTER DATABASE ENABLE BLOCK CHANGE TRACKING';
    END IF;

    DBMS_OUTPUT.PUT_LINE('Executing: ' || l_sql);
    EXECUTE IMMEDIATE l_sql;
    DBMS_OUTPUT.PUT_LINE('Block change tracking enabled.');
END;
/

PROMPT
PROMPT === Block change tracking (after action) ===
PROMPT

SELECT
    status,
    filename,
    bytes,
    ROUND(bytes / 1024 / 1024, 1) AS size_mb
FROM v$block_change_tracking;

COLUMN c_action CLEAR
COLUMN c_file CLEAR
COLUMN status CLEAR
COLUMN filename CLEAR
COLUMN bytes CLEAR
COLUMN size_mb CLEAR

SET FEEDBACK ON
SET VERIFY ON
