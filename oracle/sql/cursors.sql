/*******************************************************************************
*
* Script Name: cursors.sql
* Title: Open cursors
* Tags: Performance, Cursors, Sessions
* Purpose: List open and cached cursors by session, with SQL id and text
*
* Description:
*   Reports each session's current open-cursor count against the OPEN_CURSORS
*   limit, then lists every cursor from GV$OPEN_CURSOR. That view includes
*   currently open cursors and session-cached statements; CURSOR_TYPE
*   distinguishes the two. User sessions are shown by default. Pass a SID or
*   username to narrow the list. Press Enter at the SQL*Plus prompt if no
*   argument is passed.
*
* Parameters:
*   &1 - (Optional) SID or username. Default is all user sessions.
*
* Required Privileges:
*   - SELECT on GV$OPEN_CURSOR
*   - SELECT on GV$SESSION
*   - SELECT on GV$SESSTAT
*   - SELECT on GV$STATNAME
*   - SELECT on GV$PARAMETER
*
* Output Format:
*   - Per-session open cursor count, limit, and percent used
*   - One row per cursor: instance, SID, serial, username, type, SQL ID, text
*
* Example Usage:
*   SQL> @cursors.sql
*   SQL> @cursors.sql 142
*   SQL> @cursors.sql HR
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 220
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

COLUMN inst_id       FORMAT 999              HEADING 'Inst'
COLUMN sid           FORMAT 99999            HEADING 'SID'
COLUMN serial#       FORMAT 99999999         HEADING 'Serial#'
COLUMN username      FORMAT A20              HEADING 'Username'
COLUMN program       FORMAT A28 TRUNC        HEADING 'Program'
COLUMN open_cursors  FORMAT 999,999          HEADING 'Open'
COLUMN cursor_limit  FORMAT 999,999          HEADING 'Limit'
COLUMN pct_used      FORMAT 990.0            HEADING 'Pct'
COLUMN cursor_type   FORMAT A36              HEADING 'Cursor Type'
COLUMN sql_id        FORMAT A13              HEADING 'SQL ID'
COLUMN sql_text      FORMAT A60              HEADING 'SQL Text'

PROMPT
PROMPT Open cursor counts by session
PROMPT =============================

SELECT
    s.inst_id,
    s.sid,
    s.serial#,
    s.username,
    s.program,
    ss.value AS open_cursors,
    TO_NUMBER(p.value) AS cursor_limit,
    ROUND(ss.value / NULLIF(TO_NUMBER(p.value), 0) * 100, 1) AS pct_used
FROM gv$session s
JOIN gv$sesstat ss
  ON ss.inst_id = s.inst_id
 AND ss.sid = s.sid
JOIN gv$statname sn
  ON sn.inst_id = ss.inst_id
 AND sn.statistic# = ss.statistic#
 AND sn.name = 'opened cursors current'
JOIN gv$parameter p
  ON p.inst_id = s.inst_id
 AND p.name = 'open_cursors'
WHERE s.type = 'USER'
  AND ss.value > 0
  AND (:filter_sid IS NULL OR s.sid = :filter_sid)
  AND (:filter_user IS NULL OR s.username = :filter_user)
ORDER BY ss.value DESC, s.inst_id, s.sid;

PROMPT
PROMPT Open cursor list
PROMPT ================

SELECT
    oc.inst_id,
    oc.sid,
    s.serial#,
    s.username,
    oc.cursor_type,
    oc.sql_id,
    oc.sql_text
FROM gv$open_cursor oc
JOIN gv$session s
  ON s.inst_id = oc.inst_id
 AND s.sid = oc.sid
WHERE s.type = 'USER'
  AND (:filter_sid IS NULL OR s.sid = :filter_sid)
  AND (:filter_user IS NULL OR s.username = :filter_user)
ORDER BY oc.inst_id, oc.sid, oc.cursor_type, oc.sql_id;

UNDEFINE p_filter
UNDEFINE 1
SET FEEDBACK ON
