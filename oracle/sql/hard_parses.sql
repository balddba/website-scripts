/*******************************************************************************
*
* Script Name: hard_parses.sql
* Title: Hard parse activity
* Tags: SQL, Parse, Performance
* Purpose: Report instance and session parse ratios, plus recently hard-parsed SQL
*
* Description:
*   Reads parse counters from V$SYSSTAT (total, hard, failures, describe) and
*   computes hard/soft ratios. Session parse stats come from V$SESSTAT for a
*   SID (default current session). Recently loaded V$SQL rows with executions
*   equal to 1 are listed as likely hard parses. Cursor-cache hits are included
*   from V$SYSSTAT. Press Enter at the SQL*Plus prompts if arguments are omitted.
*
* Parameters:
*   &1 - (Optional) SID for session parse stats. Default is the current SID.
*   &2 - (Optional) Minutes of first_load_time to include. Default 60.
*
* Required Privileges:
*   - SELECT on V$SYSSTAT
*   - SELECT on V$SESSTAT
*   - SELECT on V$STATNAME
*   - SELECT on V$SESSION
*   - SELECT on V$SQL
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Instance parse counts, hard ratio, and cursor-cache hits
*   - Session parse / execute counters for the chosen SID
*   - Recent V$SQL statements with executions = 1
*
* Example Usage:
*   SQL> @hard_parses.sql
*   SQL> @hard_parses.sql 142
*   SQL> @hard_parses.sql 142 15
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

COLUMN c_sid     NEW_VALUE p_sid     NOPRINT
COLUMN c_minutes NEW_VALUE p_minutes NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), SYS_CONTEXT('USERENV', 'SID')) AS c_sid
FROM dual;
SELECT NVL(CAST(TRIM('&2') AS VARCHAR2(128)), '60') AS c_minutes FROM dual;

VARIABLE filter_sid NUMBER
VARIABLE lookback   NUMBER

BEGIN
    :filter_sid := TO_NUMBER('&&p_sid');
    :lookback   := TO_NUMBER('&&p_minutes');
END;
/

COLUMN name            FORMAT A40               HEADING 'Statistic'
COLUMN value           FORMAT 999,999,999,999   HEADING 'Value'
COLUMN parse_total     FORMAT 999,999,999,999   HEADING 'Parse Total'
COLUMN parse_hard      FORMAT 999,999,999,999   HEADING 'Hard'
COLUMN parse_fail      FORMAT 999,999,999,999   HEADING 'Failures'
COLUMN parse_describe  FORMAT 999,999,999,999   HEADING 'Describe'
COLUMN soft_parses     FORMAT 999,999,999,999   HEADING 'Soft'
COLUMN hard_pct        FORMAT 990.00            HEADING 'Hard %'
COLUMN soft_pct        FORMAT 990.00            HEADING 'Soft %'
COLUMN cache_hits      FORMAT 999,999,999,999   HEADING 'Cache Hits'
COLUMN sid             FORMAT 99999             HEADING 'SID'
COLUMN serial#         FORMAT 99999999          HEADING 'Serial#'
COLUMN username        FORMAT A20               HEADING 'Username'
COLUMN sql_id          FORMAT A13               HEADING 'SQL ID'
COLUMN child_number    FORMAT 9999              HEADING 'Child'
COLUMN plan_hash_value FORMAT 9999999999        HEADING 'Plan Hash'
COLUMN executions      FORMAT 999,999           HEADING 'Execs'
COLUMN parse_calls     FORMAT 999,999           HEADING 'Parses'
COLUMN buffer_gets     FORMAT 999,999,999       HEADING 'Buf Gets'
COLUMN elapsed_sec     FORMAT 999,990.3         HEADING 'Elapsed S'
COLUMN first_load_time FORMAT A19               HEADING 'First Load'
COLUMN parsing_schema_name FORMAT A20           HEADING 'Schema'
COLUMN sql_text        FORMAT A50 TRUNC         HEADING 'SQL Text'

PROMPT
PROMPT === Instance parse ratios ===
PROMPT

SELECT
    parse_total,
    parse_hard,
    parse_total - parse_hard AS soft_parses,
    parse_fail,
    parse_describe,
    ROUND(parse_hard / NULLIF(parse_total, 0) * 100, 2) AS hard_pct,
    ROUND((parse_total - parse_hard) / NULLIF(parse_total, 0) * 100, 2) AS soft_pct,
    cache_hits
FROM (
    SELECT
        MAX(CASE WHEN name = 'parse count (total)' THEN value END) AS parse_total,
        MAX(CASE WHEN name = 'parse count (hard)' THEN value END) AS parse_hard,
        MAX(CASE WHEN name = 'parse count (failures)' THEN value END) AS parse_fail,
        MAX(CASE WHEN name = 'parse count (describe)' THEN value END) AS parse_describe,
        MAX(CASE WHEN name = 'session cursor cache hits' THEN value END) AS cache_hits
    FROM v$sysstat
    WHERE name IN (
        'parse count (total)',
        'parse count (hard)',
        'parse count (failures)',
        'parse count (describe)',
        'session cursor cache hits'
    )
);

PROMPT
PROMPT === Session parse stats for SID &&p_sid ===
PROMPT

SELECT
    s.sid,
    s.serial#,
    s.username,
    sn.name,
    ss.value
FROM v$session s
JOIN v$sesstat ss
  ON ss.sid = s.sid
JOIN v$statname sn
  ON sn.statistic# = ss.statistic#
WHERE s.sid = :filter_sid
  AND sn.name IN (
        'parse count (total)',
        'parse count (hard)',
        'parse count (failures)',
        'parse count (describe)',
        'execute count',
        'session cursor cache hits',
        'session cursor cache count',
        'opened cursors current'
      )
ORDER BY
    DECODE(
        sn.name,
        'parse count (total)', 1,
        'parse count (hard)', 2,
        'parse count (failures)', 3,
        'parse count (describe)', 4,
        'execute count', 5,
        'session cursor cache hits', 6,
        'session cursor cache count', 7,
        'opened cursors current', 8,
        9
    );

PROMPT
PROMPT === Recently loaded SQL with executions = 1 (last &&p_minutes minutes) ===
PROMPT

SELECT
    q.sql_id,
    q.child_number,
    q.plan_hash_value,
    q.parsing_schema_name,
    q.executions,
    q.parse_calls,
    q.buffer_gets,
    ROUND(q.elapsed_time / 1e6, 3) AS elapsed_sec,
    q.first_load_time,
    q.sql_text
FROM v$sql q
WHERE q.executions <= 1
  AND q.parse_calls >= 1
  AND q.first_load_time >= TO_CHAR(SYSDATE - (:lookback / 1440), 'YYYY-MM-DD/HH24:MI:SS')
  AND q.parsing_schema_name NOT IN ('SYS', 'SYSTEM')
ORDER BY q.first_load_time DESC, q.buffer_gets DESC;

COLUMN name CLEAR
COLUMN value CLEAR
COLUMN parse_total CLEAR
COLUMN parse_hard CLEAR
COLUMN parse_fail CLEAR
COLUMN parse_describe CLEAR
COLUMN soft_parses CLEAR
COLUMN hard_pct CLEAR
COLUMN soft_pct CLEAR
COLUMN cache_hits CLEAR
COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN username CLEAR
COLUMN sql_id CLEAR
COLUMN child_number CLEAR
COLUMN plan_hash_value CLEAR
COLUMN executions CLEAR
COLUMN parse_calls CLEAR
COLUMN buffer_gets CLEAR
COLUMN elapsed_sec CLEAR
COLUMN first_load_time CLEAR
COLUMN parsing_schema_name CLEAR
COLUMN sql_text CLEAR

UNDEFINE p_sid
UNDEFINE p_minutes
UNDEFINE 1
UNDEFINE 2
SET FEEDBACK ON
SET VERIFY ON
