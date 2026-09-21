/*******************************************************************************
*
* Script Name: session_info.sql
* Title: Session information
* Tags: Sessions
* Purpose: Show detailed user session attributes, wait state, and SQL identifiers
*
* Description:
*   Reports SID, serial number, identity, client, service, module/action, wait
*   event, and current SQL for sessions in V$SESSION. User sessions are listed
*   by default. Pass a SID or username to narrow the list; a SID also shows
*   background processes. sessions.sql remains the compact RAC listing with OS
*   process ID for ALTER SYSTEM KILL SESSION. Press Enter at the SQL*Plus
*   prompt if no argument is passed.
*
* Parameters:
*   &1 - (Optional) SID or username. Default is all user sessions.
*
* Required Privileges:
*   - SELECT on V$SESSION
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - SID, serial number, username, OS user, machine, and program
*   - Status, type, logon time, and seconds since last call
*   - Wait event, wait class, SQL ID, service, module, action, and schema
*
* Example Usage:
*   SQL> @session_info.sql
*   SQL> @session_info.sql 142
*   SQL> @session_info.sql HR
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 300
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

-- Optional &1: SQL*Plus prompts if omitted; Enter (empty) means all user sessions.
COLUMN c_filter NEW_VALUE p_filter NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), '%') AS c_filter FROM dual;

VARIABLE filter_sid  NUMBER
VARIABLE filter_user VARCHAR2(128)

BEGIN
    -- '%' lists every user session; digits are a SID; anything else is a username.
    IF '&&p_filter' = '%' THEN
        :filter_sid  := NULL;
        :filter_user := NULL;
    ELSIF REGEXP_LIKE('&&p_filter', '^[0-9]+$') THEN
        :filter_sid  := TO_NUMBER('&&p_filter');
        :filter_user := NULL;
    ELSE
        :filter_sid  := NULL;
        :filter_user := UPPER('&&p_filter');
    END IF;
END;
/

COLUMN sid          FORMAT 99999            HEADING 'SID'
COLUMN serial#      FORMAT 99999999         HEADING 'Serial#'
COLUMN username     FORMAT A20              HEADING 'Username'
COLUMN osuser       FORMAT A16 TRUNC        HEADING 'OS User'
COLUMN machine      FORMAT A28 TRUNC        HEADING 'Machine'
COLUMN program      FORMAT A28 TRUNC        HEADING 'Program'
COLUMN status       FORMAT A8               HEADING 'Status'
COLUMN type         FORMAT A10              HEADING 'Type'
COLUMN logon_time   FORMAT A19              HEADING 'Logon Time'
COLUMN last_call_et FORMAT 999,999,999      HEADING 'Last Call'
COLUMN event        FORMAT A32 TRUNC        HEADING 'Event'
COLUMN wait_class   FORMAT A14              HEADING 'Wait Class'
COLUMN sql_id       FORMAT A13              HEADING 'SQL ID'
COLUMN service_name FORMAT A20 TRUNC        HEADING 'Service'
COLUMN module       FORMAT A20 TRUNC        HEADING 'Module'
COLUMN action       FORMAT A20 TRUNC        HEADING 'Action'
COLUMN schemaname   FORMAT A20              HEADING 'Schema'

PROMPT
PROMPT === Session information ===
PROMPT

SELECT
    s.sid,
    s.serial#,
    s.username,
    s.osuser,
    s.machine,
    s.program,
    s.status,
    s.type,
    s.logon_time,
    s.last_call_et,
    s.event,
    s.wait_class,
    s.sql_id,
    s.service_name,
    s.module,
    s.action,
    s.schemaname
FROM v$session s
WHERE (
        :filter_sid IS NOT NULL
        OR :filter_user IS NOT NULL
        OR s.type = 'USER'
      )
  AND (:filter_sid IS NULL OR s.sid = :filter_sid)
  AND (:filter_user IS NULL OR s.username = :filter_user)
ORDER BY
    DECODE(s.status, 'ACTIVE', 1, 'INACTIVE', 2, 3),
    s.username,
    s.sid;

COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN username CLEAR
COLUMN osuser CLEAR
COLUMN machine CLEAR
COLUMN program CLEAR
COLUMN status CLEAR
COLUMN type CLEAR
COLUMN logon_time CLEAR
COLUMN last_call_et CLEAR
COLUMN event CLEAR
COLUMN wait_class CLEAR
COLUMN sql_id CLEAR
COLUMN service_name CLEAR
COLUMN module CLEAR
COLUMN action CLEAR
COLUMN schemaname CLEAR

UNDEFINE p_filter
UNDEFINE 1
SET FEEDBACK ON
SET VERIFY ON
