/*******************************************************************************
*
* Script Name: session_stats.sql
* Title: Session statistics
* Tags: Sessions, Statistics
* Purpose: Display V$SESSTAT counters for a SID, with a useful default set or a name pattern
*
* Description:
*   Joins V$SESSTAT to V$STATNAME for one session. With no statistic filter,
*   a default set is shown: CPU, parses, executes, logical and physical reads,
*   block gets, redo, sorts, commits, and PGA. Pass ALL to list every non-zero
*   statistic, or a LIKE pattern (use % wildcards) to match names. CPU used by
*   this session is in centiseconds. Defaults to the current session SID.
*   Press Enter at the SQL*Plus prompts if arguments are omitted.
*
* Parameters:
*   &1 - (Optional) SID. Default is the current session SID.
*   &2 - (Optional) ALL, or a statistic-name pattern. Default is the useful set.
*
* Required Privileges:
*   - SELECT on V$SESSTAT
*   - SELECT on V$STATNAME
*   - SELECT on V$SESSION
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - SID, serial number, username, statistic number, name, and value
*
* Example Usage:
*   SQL> @session_stats.sql
*   SQL> @session_stats.sql 142
*   SQL> @session_stats.sql 142 parse%
*   SQL> @session_stats.sql 142 ALL
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 160
SET PAGESIZE 200
SET TRIMSPOOL ON
SET TAB OFF

COLUMN c_sid    NEW_VALUE p_sid    NOPRINT
COLUMN c_filter NEW_VALUE p_filter NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), SYS_CONTEXT('USERENV', 'SID')) AS c_sid
FROM dual;
SELECT NVL(CAST(TRIM('&2') AS VARCHAR2(128)), 'DEFAULT') AS c_filter FROM dual;

VARIABLE filter_sid     NUMBER
VARIABLE filter_mode    VARCHAR2(10)
VARIABLE filter_pattern VARCHAR2(128)

BEGIN
    :filter_sid := TO_NUMBER('&&p_sid');

    IF UPPER('&&p_filter') = 'DEFAULT' THEN
        :filter_mode    := 'DEFAULT';
        :filter_pattern := NULL;
    ELSIF UPPER('&&p_filter') IN ('ALL', '%') THEN
        :filter_mode    := 'ALL';
        :filter_pattern := '%';
    ELSE
        :filter_mode    := 'PATTERN';
        :filter_pattern := LOWER('&&p_filter');
    END IF;
END;
/

COLUMN sid        FORMAT 99999            HEADING 'SID'
COLUMN serial#    FORMAT 99999999         HEADING 'Serial#'
COLUMN username   FORMAT A20              HEADING 'Username'
COLUMN statistic# FORMAT 99999            HEADING 'Stat#'
COLUMN name       FORMAT A64              HEADING 'Statistic'
COLUMN value      FORMAT 999,999,999,999  HEADING 'Value'

PROMPT
PROMPT === Session statistics for SID &&p_sid ===
PROMPT

SELECT
    s.sid,
    s.serial#,
    s.username,
    ss.statistic#,
    sn.name,
    ss.value
FROM v$session s
JOIN v$sesstat ss
  ON ss.sid = s.sid
JOIN v$statname sn
  ON sn.statistic# = ss.statistic#
WHERE s.sid = :filter_sid
  AND (
        (:filter_mode = 'DEFAULT'
         AND sn.name IN (
                'CPU used by this session',
                'parse count (total)',
                'parse count (hard)',
                'parse count (failures)',
                'execute count',
                'user calls',
                'session logical reads',
                'physical reads',
                'physical reads direct',
                'db block gets',
                'consistent gets',
                'db block changes',
                'redo size',
                'sorts (memory)',
                'sorts (disk)',
                'user commits',
                'user rollbacks',
                'opened cursors current',
                'session pga memory',
                'session pga memory max'
            ))
        OR (:filter_mode = 'ALL' AND ss.value <> 0)
        OR (:filter_mode = 'PATTERN' AND LOWER(sn.name) LIKE :filter_pattern)
      )
ORDER BY
    CASE
        WHEN :filter_mode = 'DEFAULT' THEN
            DECODE(
                sn.name,
                'CPU used by this session', 1,
                'parse count (total)', 2,
                'parse count (hard)', 3,
                'parse count (failures)', 4,
                'execute count', 5,
                'user calls', 6,
                'session logical reads', 7,
                'physical reads', 8,
                'physical reads direct', 9,
                'db block gets', 10,
                'consistent gets', 11,
                'db block changes', 12,
                'redo size', 13,
                'sorts (memory)', 14,
                'sorts (disk)', 15,
                'user commits', 16,
                'user rollbacks', 17,
                'opened cursors current', 18,
                'session pga memory', 19,
                'session pga memory max', 20,
                99
            )
        ELSE ss.statistic#
    END,
    sn.name;

COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN username CLEAR
COLUMN statistic# CLEAR
COLUMN name CLEAR
COLUMN value CLEAR

UNDEFINE p_sid
UNDEFINE p_filter
UNDEFINE 1
UNDEFINE 2
SET FEEDBACK ON
SET VERIFY ON
