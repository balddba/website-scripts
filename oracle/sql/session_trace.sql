/*******************************************************************************
*
* Script Name: session_trace.sql
* Title: Session SQL trace
* Tags: Sessions, Trace, Diagnostics
* Purpose: Enable or disable SQL trace for the current session or another SID,SERIAL#
*
* Description:
*   Calls DBMS_MONITOR.SESSION_TRACE_ENABLE or SESSION_TRACE_DISABLE. Waits and
*   binds are recorded by default. Omit SID and SERIAL# to trace the current
*   session; pass both (or SID alone) to trace another session. After ENABLE,
*   the process TRACEFILE from V$PROCESS is printed so the dump can be found.
*   Prefer DBMS_MONITOR over ALTER SESSION SET SQL_TRACE. Press Enter at the
*   SQL*Plus prompts to accept defaults.
*
* Parameters:
*   &1 - Action: ENABLE or DISABLE (required)
*   &2 - (Optional) SID. Default is the current session.
*   &3 - (Optional) SERIAL#. Looked up from V$SESSION when omitted.
*   &4 - (Optional) waits TRUE/FALSE. Default TRUE. ENABLE only.
*   &5 - (Optional) binds TRUE/FALSE. Default TRUE. ENABLE only.
*
* Required Privileges:
*   - EXECUTE on DBMS_MONITOR
*   - SELECT on V$SESSION
*   - SELECT on V$PROCESS
*   - SELECT on V$DIAG_INFO
*   - Or DBA / SELECT_CATALOG_ROLE plus EXECUTE on DBMS_MONITOR
*
* Output Format:
*   - Confirmation of ENABLE or DISABLE for SID,SERIAL#
*   - Tracefile path from V$PROCESS
*   - Default Trace File from V$DIAG_INFO when tracing the current session
*
* Example Usage:
*   SQL> @session_trace.sql ENABLE
*   SQL> @session_trace.sql DISABLE
*   SQL> @session_trace.sql ENABLE 142 33891
*   SQL> @session_trace.sql ENABLE 142 33891 TRUE FALSE
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET SERVEROUTPUT ON SIZE UNLIMITED
SET LINESIZE 220
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN c_action NEW_VALUE p_action NOPRINT
COLUMN c_sid    NEW_VALUE p_sid    NOPRINT
COLUMN c_serial NEW_VALUE p_serial NOPRINT
COLUMN c_waits  NEW_VALUE p_waits  NOPRINT
COLUMN c_binds  NEW_VALUE p_binds  NOPRINT

SELECT UPPER(TRIM('&1')) AS c_action FROM dual;
SELECT NVL(CAST(TRIM('&2') AS VARCHAR2(128)), 'CURRENT') AS c_sid FROM dual;
SELECT NVL(CAST(TRIM('&3') AS VARCHAR2(128)), 'LOOKUP') AS c_serial FROM dual;
SELECT NVL(CAST(UPPER(TRIM('&4')) AS VARCHAR2(128)), 'TRUE') AS c_waits FROM dual;
SELECT NVL(CAST(UPPER(TRIM('&5')) AS VARCHAR2(128)), 'TRUE') AS c_binds FROM dual;

VARIABLE target_sid    NUMBER
VARIABLE target_serial NUMBER

DECLARE
    l_action     VARCHAR2(20) := '&&p_action';
    l_sid_arg    VARCHAR2(20) := '&&p_sid';
    l_serial_arg VARCHAR2(20) := '&&p_serial';
    l_waits_arg  VARCHAR2(10) := '&&p_waits';
    l_binds_arg  VARCHAR2(10) := '&&p_binds';
    l_sid        NUMBER;
    l_serial     NUMBER;
    l_username   VARCHAR2(128);
    l_program    VARCHAR2(256);
    l_tracefile  VARCHAR2(512);
    l_waits      BOOLEAN;
    l_binds      BOOLEAN;
    l_is_current BOOLEAN := FALSE;

    FUNCTION to_bool(p_val VARCHAR2) RETURN BOOLEAN IS
    BEGIN
        RETURN UPPER(p_val) IN ('TRUE', 'T', 'YES', 'Y', '1');
    END to_bool;
BEGIN
    IF l_action IS NULL OR l_action NOT IN ('ENABLE', 'DISABLE') THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Action must be ENABLE or DISABLE.'
        );
    END IF;

    IF l_sid_arg = 'CURRENT' THEN
        SELECT s.sid, s.serial#, s.username, s.program
          INTO l_sid, l_serial, l_username, l_program
          FROM v$session s
         WHERE s.sid = SYS_CONTEXT('USERENV', 'SID');
        l_is_current := TRUE;
    ELSE
        l_sid := TO_NUMBER(l_sid_arg);
        IF l_serial_arg = 'LOOKUP' THEN
            SELECT s.serial#, s.username, s.program
              INTO l_serial, l_username, l_program
              FROM v$session s
             WHERE s.sid = l_sid;
        ELSE
            l_serial := TO_NUMBER(l_serial_arg);
            SELECT s.username, s.program
              INTO l_username, l_program
              FROM v$session s
             WHERE s.sid = l_sid
               AND s.serial# = l_serial;
        END IF;
        l_is_current := (l_sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID')));
    END IF;

    :target_sid    := l_sid;
    :target_serial := l_serial;

    l_waits := to_bool(l_waits_arg);
    l_binds := to_bool(l_binds_arg);

    IF l_action = 'ENABLE' THEN
        DBMS_MONITOR.SESSION_TRACE_ENABLE(
            session_id => l_sid,
            serial_num => l_serial,
            waits      => l_waits,
            binds      => l_binds
        );
        DBMS_OUTPUT.PUT_LINE(
            'Enabled SQL trace for SID=' || l_sid
            || ',SERIAL#=' || l_serial
            || ' user=' || NVL(l_username, '-')
            || ' program=' || NVL(l_program, '-')
            || ' waits=' || CASE WHEN l_waits THEN 'TRUE' ELSE 'FALSE' END
            || ' binds=' || CASE WHEN l_binds THEN 'TRUE' ELSE 'FALSE' END
        );
    ELSE
        DBMS_MONITOR.SESSION_TRACE_DISABLE(
            session_id => l_sid,
            serial_num => l_serial
        );
        DBMS_OUTPUT.PUT_LINE(
            'Disabled SQL trace for SID=' || l_sid
            || ',SERIAL#=' || l_serial
            || ' user=' || NVL(l_username, '-')
        );
    END IF;

    SELECT p.tracefile
      INTO l_tracefile
      FROM v$session s
      JOIN v$process p
        ON p.addr = s.paddr
     WHERE s.sid = l_sid
       AND s.serial# = l_serial;

    DBMS_OUTPUT.PUT_LINE('Trace file: ' || NVL(l_tracefile, '(not found)'));

    IF l_is_current THEN
        FOR r IN (
            SELECT name, value
            FROM v$diag_info
            WHERE name IN ('Default Trace File', 'Session ID')
            ORDER BY name
        ) LOOP
            DBMS_OUTPUT.PUT_LINE(r.name || ': ' || r.value);
        END LOOP;
    END IF;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Session SID=' || NVL(l_sid_arg, '?')
            || ' SERIAL#=' || NVL(l_serial_arg, '?')
            || ' was not found.'
        );
    WHEN TOO_MANY_ROWS THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'More than one session matched SID=' || l_sid_arg
            || '; pass SERIAL# as the third argument.'
        );
END;
/

COLUMN sid        FORMAT 99999     HEADING 'SID'
COLUMN serial#    FORMAT 99999999  HEADING 'Serial#'
COLUMN sql_trace  FORMAT A10       HEADING 'SQL Trace'
COLUMN tracefile  FORMAT A120      HEADING 'Trace File'

PROMPT
PROMPT === Session trace status ===
PROMPT

SELECT
    s.sid,
    s.serial#,
    s.sql_trace,
    p.tracefile
FROM v$session s
JOIN v$process p
  ON p.addr = s.paddr
WHERE s.sid = :target_sid
  AND s.serial# = :target_serial;

COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN sql_trace CLEAR
COLUMN tracefile CLEAR

UNDEFINE p_action
UNDEFINE p_sid
UNDEFINE p_serial
UNDEFINE p_waits
UNDEFINE p_binds
UNDEFINE 1
UNDEFINE 2
UNDEFINE 3
UNDEFINE 4
UNDEFINE 5
SET SERVEROUTPUT OFF
SET FEEDBACK ON
SET VERIFY ON
