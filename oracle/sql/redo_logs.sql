/*******************************************************************************
*
* Script Name: redo_logs.sql
* Title: Redo log groups and members
* Tags: Redo, Backup
* Purpose: Show online redo groups, members, and recent log history
*
* Description:
*   Lists each online redo log group from V$LOG (thread, sequence, size,
*   archived flag, status) with every member from V$LOGFILE. Current groups
*   have STATUS = CURRENT. Recent V$LOG_HISTORY rows show archived sequence
*   times. On RAC, groups are per thread. Standby redo logs are not included;
*   use dg_primary.sql or dg_standby.sql for those.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$LOG
*   - SELECT on V$LOGFILE
*   - SELECT on V$LOG_HISTORY
*   - SELECT on V$THREAD
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Redo threads
*   - Groups with sequence, size, archived, and status
*   - Members (path, type, member status)
*   - Last 50 log history rows
*
* Example Usage:
*   SQL> @redo_logs.sql
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

COLUMN thread#          FORMAT 9990              HEADING 'Thr'
COLUMN thread_status    FORMAT A10               HEADING 'Status'
COLUMN enabled          FORMAT A12               HEADING 'Enabled'
COLUMN groups           FORMAT 9990              HEADING 'Groups'
COLUMN instance         FORMAT A16               HEADING 'Instance'
COLUMN sequence#        FORMAT 999999990         HEADING 'Seq'
COLUMN group#           FORMAT 9990              HEADING 'Grp'
COLUMN size_mb          FORMAT 999,999,990       HEADING 'MB'
COLUMN blocksize        FORMAT 99990             HEADING 'Blk'
COLUMN members          FORMAT 9990              HEADING 'Mem'
COLUMN archived         FORMAT A8                HEADING 'Archived'
COLUMN status           FORMAT A10               HEADING 'Status'
COLUMN member           FORMAT A80               HEADING 'Member'
COLUMN type             FORMAT A16               HEADING 'Type'
COLUMN member_status    FORMAT A10               HEADING 'Mem Status'
COLUMN is_recovery_dest_file FORMAT A8           HEADING 'FRA'
COLUMN first_time       FORMAT A19               HEADING 'First Time'
COLUMN next_time        FORMAT A19               HEADING 'Next Time'
COLUMN first_change#    FORMAT 999999999999999   HEADING 'First SCN'
COLUMN next_change#     FORMAT 999999999999999   HEADING 'Next SCN'

PROMPT
PROMPT === Threads ===
PROMPT

SELECT
    thread#,
    status AS thread_status,
    enabled,
    groups,
    instance,
    sequence#
FROM v$thread
ORDER BY thread#;

PROMPT
PROMPT === Online redo log groups ===
PROMPT

SELECT
    group#,
    thread#,
    sequence#,
    ROUND(bytes / 1024 / 1024) AS size_mb,
    blocksize,
    members,
    archived,
    status
FROM v$log
ORDER BY thread#, group#;

PROMPT
PROMPT === Redo log members ===
PROMPT

SELECT
    l.group#,
    l.thread#,
    l.status,
    f.type,
    f.status AS member_status,
    f.is_recovery_dest_file,
    f.member
FROM v$log l
JOIN v$logfile f
    ON f.group# = l.group#
ORDER BY
    l.thread#,
    l.group#,
    f.member;

PROMPT
PROMPT === Recent log history (last 50) ===
PROMPT

SELECT
    thread#,
    sequence#,
    TO_CHAR(first_time, 'YYYY-MM-DD HH24:MI:SS') AS first_time,
    TO_CHAR(next_time, 'YYYY-MM-DD HH24:MI:SS') AS next_time,
    first_change#,
    next_change#
FROM (
    SELECT
        thread#,
        sequence#,
        first_time,
        LEAD(first_time) OVER (
            PARTITION BY thread# ORDER BY sequence#
        ) AS next_time,
        first_change#,
        next_change#
    FROM v$log_history
    ORDER BY first_time DESC
)
WHERE ROWNUM <= 50
ORDER BY first_time, thread#, sequence#;

COLUMN thread# CLEAR
COLUMN thread_status CLEAR
COLUMN enabled CLEAR
COLUMN groups CLEAR
COLUMN instance CLEAR
COLUMN sequence# CLEAR
COLUMN group# CLEAR
COLUMN size_mb CLEAR
COLUMN blocksize CLEAR
COLUMN members CLEAR
COLUMN archived CLEAR
COLUMN status CLEAR
COLUMN member CLEAR
COLUMN type CLEAR
COLUMN member_status CLEAR
COLUMN is_recovery_dest_file CLEAR
COLUMN first_time CLEAR
COLUMN next_time CLEAR
COLUMN first_change# CLEAR
COLUMN next_change# CLEAR

SET FEEDBACK ON
SET VERIFY ON
