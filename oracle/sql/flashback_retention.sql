/*******************************************************************************
*
* Script Name: flashback_retention.sql
* Title: Flashback Retention Status
* Tags: Flashback, Backup, Recovery
* Purpose: Monitors Flashback Database retention target vs. actual, oldest SCN/time, and log generation rate from gv$flashback_database_log and gv$flashback_database_stat.
*
* Description:
*   Monitors Flashback Database retention configuration, comparing the
*   configured retention target against the actual oldest flashback time
*   and SCN. Evaluates flashback log sizing, recovery area usage, and
*   hourly generation rates from GV$FLASHBACK_DATABASE_LOG and
*   GV$FLASHBACK_DATABASE_STAT.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$DATABASE
*   - SELECT on V$PARAMETER
*   - SELECT on GV$FLASHBACK_DATABASE_LOG
*   - SELECT on GV$FLASHBACK_DATABASE_STAT
*   - SELECT on V$RECOVERY_FILE_DEST
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Flashback database status and recovery parameters
*   - Flashback log retention target vs. actual retention
*   - Fast Recovery Area (FRA) space and flashback proportion
*   - Hourly flashback log generation statistics (GV$FLASHBACK_DATABASE_STAT)
*
* Example Usage:
*   sqlplus user/password@yourdb @flashback_retention.sql
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

COLUMN db_name            FORMAT A16             HEADING 'DB Name'
COLUMN log_mode           FORMAT A12             HEADING 'Log Mode'
COLUMN flashback_on       FORMAT A12             HEADING 'Flashback On'
COLUMN parameter          FORMAT A32             HEADING 'Parameter'
COLUMN param_value        FORMAT A45             HEADING 'Value'
COLUMN oldest_scn         FORMAT 999999999999999 HEADING 'Oldest SCN'
COLUMN oldest_time        FORMAT A19             HEADING 'Oldest Flashback'
COLUMN target_min         FORMAT 999,999         HEADING 'Target (Min)'
COLUMN actual_min         FORMAT 999,999.0       HEADING 'Actual (Min)'
COLUMN target_met         FORMAT A12             HEADING 'Target Met?'
COLUMN size_mb            FORMAT 999,999,990.0   HEADING 'Size MB'
COLUMN est_size_mb        FORMAT 999,999,990.0   HEADING 'Est Size MB'
COLUMN fra_name           FORMAT A30             HEADING 'FRA Location'
COLUMN space_limit_gb     FORMAT 999,999,990.0   HEADING 'Limit GB'
COLUMN space_used_gb      FORMAT 999,999,990.0   HEADING 'Used GB'
COLUMN pct_used           FORMAT 990.0           HEADING 'Pct Used'
COLUMN inst_id            FORMAT 9990            HEADING 'Inst'
COLUMN begin_time         FORMAT A19             HEADING 'Begin Time'
COLUMN end_time           FORMAT A19             HEADING 'End Time'
COLUMN fb_data_mb         FORMAT 999,999,990.0   HEADING 'Flashback MB'
COLUMN db_data_mb         FORMAT 999,999,990.0   HEADING 'DB Data MB'
COLUMN redo_data_mb       FORMAT 999,999,990.0   HEADING 'Redo MB'
COLUMN fb_rate_mb_hr      FORMAT 999,990.0       HEADING 'FB Rate MB/hr'

PROMPT
PROMPT ===============================================================================
PROMPT Flashback Retention Status
PROMPT ===============================================================================

PROMPT
PROMPT === Database Flashback Configuration ===
PROMPT

SELECT
    name AS db_name,
    log_mode,
    flashback_on
FROM v$database;

PROMPT
PROMPT === Flashback & Recovery Parameters ===
PROMPT

SELECT
    name AS parameter,
    NVL(display_value, '(not set)') AS param_value
FROM v$parameter
WHERE name IN (
    'db_recovery_file_dest',
    'db_recovery_file_dest_size',
    'db_flashback_retention_target'
)
ORDER BY name;

PROMPT
PROMPT === Flashback Retention Target vs. Actual ===
PROMPT

SELECT
    oldest_flashback_scn AS oldest_scn,
    TO_CHAR(oldest_flashback_time, 'YYYY-MM-DD HH24:MI:SS') AS oldest_time,
    retention_target AS target_min,
    ROUND((SYSDATE - oldest_flashback_time) * 1440, 1) AS actual_min,
    CASE
        WHEN oldest_flashback_time IS NULL THEN 'NO DATA'
        WHEN (SYSDATE - oldest_flashback_time) * 1440 >= retention_target THEN 'YES'
        ELSE 'NO (SHORT)'
    END AS target_met,
    ROUND(flashback_size / 1024 / 1024, 1) AS size_mb,
    ROUND(estimated_flashback_size / 1024 / 1024, 1) AS est_size_mb
FROM v$flashback_database_log;

PROMPT
PROMPT === Fast Recovery Area Space ===
PROMPT

SELECT
    name AS fra_name,
    ROUND(space_limit / 1024 / 1024 / 1024, 1) AS space_limit_gb,
    ROUND(space_used / 1024 / 1024 / 1024, 1) AS space_used_gb,
    ROUND(space_used / NULLIF(space_limit, 0) * 100, 1) AS pct_used
FROM v$recovery_file_dest;

PROMPT
PROMPT === Flashback Generation Statistics (GV$FLASHBACK_DATABASE_STAT) ===
PROMPT

SELECT
    inst_id,
    TO_CHAR(begin_time, 'YYYY-MM-DD HH24:MI:SS') AS begin_time,
    TO_CHAR(end_time, 'YYYY-MM-DD HH24:MI:SS') AS end_time,
    ROUND(flashback_data / 1024 / 1024, 1) AS fb_data_mb,
    ROUND(db_data / 1024 / 1024, 1) AS db_data_mb,
    ROUND(redo_data / 1024 / 1024, 1) AS redo_data_mb,
    ROUND(flashback_data / 1024 / 1024 / NULLIF((end_time - begin_time) * 24, 0), 1) AS fb_rate_mb_hr
FROM (
    SELECT
        inst_id,
        begin_time,
        end_time,
        flashback_data,
        db_data,
        redo_data
    FROM gv$flashback_database_stat
    ORDER BY begin_time DESC, inst_id
)
WHERE ROWNUM <= 24;

COLUMN db_name CLEAR
COLUMN log_mode CLEAR
COLUMN flashback_on CLEAR
COLUMN parameter CLEAR
COLUMN param_value CLEAR
COLUMN oldest_scn CLEAR
COLUMN oldest_time CLEAR
COLUMN target_min CLEAR
COLUMN actual_min CLEAR
COLUMN target_met CLEAR
COLUMN size_mb CLEAR
COLUMN est_size_mb CLEAR
COLUMN fra_name CLEAR
COLUMN space_limit_gb CLEAR
COLUMN space_used_gb CLEAR
COLUMN pct_used CLEAR
COLUMN inst_id CLEAR
COLUMN begin_time CLEAR
COLUMN end_time CLEAR
COLUMN fb_data_mb CLEAR
COLUMN db_data_mb CLEAR
COLUMN redo_data_mb CLEAR
COLUMN fb_rate_mb_hr CLEAR

SET FEEDBACK ON
SET VERIFY ON
