/*******************************************************************************
*
* Script Name: undo_tuning.sql
* Title: Undo Tablespace Tuning
* Tags: Storage, Undo, Tuning
* Purpose: Evaluates undo retention health, unexpired steal counts, undo generation rate, and sizing from gv$undostat.
*
* Description:
*   Evaluates undo tablespace sizing, retention health, undo generation rate,
*   and unexpired block steals from GV$UNDOSTAT, DBA_TABLESPACES, and
*   DBA_UNDO_EXTENTS. Helps diagnose ORA-01555 (snapshot too old) errors,
*   space pressure, and optimal undo retention configuration.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on GV$UNDOSTAT
*   - SELECT on DBA_TABLESPACES
*   - SELECT on DBA_DATA_FILES
*   - SELECT on DBA_UNDO_EXTENTS
*   - SELECT on V$PARAMETER
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Undo configuration parameters (management, retention, tablespace)
*   - Undo tablespace space allocation and autoextend status
*   - Undo extents status breakdown (ACTIVE, UNEXPIRED, EXPIRED)
*   - Undo statistics health summary (peak rate, max query, steal counts, ORA-01555)
*   - Undo tablespace sizing recommendation
*   - Recent undo activity intervals (GV$UNDOSTAT)
*
* Example Usage:
*   sqlplus user/password@yourdb @undo_tuning.sql
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

COLUMN inst_id            FORMAT 9990            HEADING 'Inst'
COLUMN parameter          FORMAT A30             HEADING 'Parameter'
COLUMN param_value        FORMAT A40             HEADING 'Value'
COLUMN tablespace_name    FORMAT A25             HEADING 'Tablespace'
COLUMN retention          FORMAT A15             HEADING 'Retention'
COLUMN total_mb           FORMAT 999,999,990.0   HEADING 'Total MB'
COLUMN autoextensible     FORMAT A10             HEADING 'Autoextend'
COLUMN status             FORMAT A15             HEADING 'Extent Status'
COLUMN extent_mb          FORMAT 999,999,990.0   HEADING 'Extent MB'
COLUMN extent_count       FORMAT 999,999,990     HEADING 'Extents'
COLUMN metric             FORMAT A40             HEADING 'Metric'
COLUMN metric_value       FORMAT A35             HEADING 'Value'
COLUMN begin_time         FORMAT A19             HEADING 'Begin Time'
COLUMN end_time           FORMAT A19             HEADING 'End Time'
COLUMN undoblks           FORMAT 999,999,990     HEADING 'Undo Blks'
COLUMN txncount           FORMAT 999,999,990     HEADING 'Txn Count'
COLUMN maxquerylen        FORMAT 999,999,990     HEADING 'Max Query (s)'
COLUMN tuned_undoretention FORMAT 999,999,990    HEADING 'Tuned Ret (s)'
COLUMN unxpstealcnt       FORMAT 999,990         HEADING 'Unxp Steals'
COLUMN expstealcnt        FORMAT 999,990         HEADING 'Exp Steals'
COLUMN ssolderrcnt        FORMAT 999,990         HEADING 'ORA-01555'
COLUMN nospaceerrcnt      FORMAT 999,990         HEADING 'No Space'
COLUMN rec_undo_mb        FORMAT 999,999,990.0   HEADING 'Rec Undo MB'
COLUMN current_undo_mb    FORMAT 999,999,990.0   HEADING 'Current MB'
COLUMN rec_status         FORMAT A30             HEADING 'Sizing Assessment'

PROMPT
PROMPT ===============================================================================
PROMPT Undo Tablespace Tuning
PROMPT ===============================================================================

PROMPT
PROMPT === Undo Configuration Parameters ===
PROMPT

SELECT
    name AS parameter,
    value AS param_value
FROM v$parameter
WHERE name IN (
    'undo_management',
    'undo_tablespace',
    'undo_retention',
    'undo_retention_high',
    'local_undo_enabled'
)
ORDER BY name;

PROMPT
PROMPT === Undo Tablespace Allocation ===
PROMPT

SELECT
    t.tablespace_name,
    t.retention,
    ROUND(SUM(f.bytes) / 1024 / 1024, 1) AS total_mb,
    MAX(f.autoextensible) AS autoextensible
FROM dba_tablespaces t
JOIN dba_data_files f ON t.tablespace_name = f.tablespace_name
WHERE t.contents = 'UNDO'
GROUP BY t.tablespace_name, t.retention
ORDER BY t.tablespace_name;

PROMPT
PROMPT === Undo Extent Status Breakdown ===
PROMPT

SELECT
    tablespace_name,
    status,
    ROUND(SUM(bytes) / 1024 / 1024, 1) AS extent_mb,
    COUNT(*) AS extent_count
FROM dba_undo_extents
GROUP BY tablespace_name, status
ORDER BY tablespace_name, status;

PROMPT
PROMPT === Undo Health Summary (Last 7 Days / Available History) ===
PROMPT

SELECT metric, metric_value
FROM (
    SELECT 10 AS n, 'Total Undo Blocks Generated' AS metric, TO_CHAR(NVL(SUM(undoblks), 0), '999,999,999,990') AS metric_value FROM gv$undostat
    UNION ALL
    SELECT 20, 'Total Transactions Executed', TO_CHAR(NVL(SUM(txncount), 0), '999,999,999,990') FROM gv$undostat
    UNION ALL
    SELECT 30, 'Max Query Duration (seconds)', TO_CHAR(NVL(MAX(maxquerylen), 0), '999,999,990') FROM gv$undostat
    UNION ALL
    SELECT 40, 'Peak Undo Rate (blocks/sec)', TO_CHAR(NVL(MAX(undoblks / NULLIF(TO_NUMBER(SUBSTR((end_time - begin_time) * 86400, 1, 10)), 0)), 0), '999,990.0') FROM gv$undostat
    UNION ALL
    SELECT 50, 'Average Tuned Retention (seconds)', TO_CHAR(NVL(AVG(tuned_undoretention), 0), '999,999,990') FROM gv$undostat
    UNION ALL
    SELECT 60, 'Minimum Tuned Retention (seconds)', TO_CHAR(NVL(MIN(tuned_undoretention), 0), '999,999,990') FROM gv$undostat
    UNION ALL
    SELECT 70, 'Unexpired Block Steals (unxpstealcnt)', TO_CHAR(NVL(SUM(unxpstealcnt), 0), '999,999,990') FROM gv$undostat
    UNION ALL
    SELECT 80, 'Expired Block Steals (expstealcnt)', TO_CHAR(NVL(SUM(expstealcnt), 0), '999,999,990') FROM gv$undostat
    UNION ALL
    SELECT 90, 'Snapshot Too Old Errors (ssolderrcnt)', TO_CHAR(NVL(SUM(ssolderrcnt), 0), '999,999,990') FROM gv$undostat
    UNION ALL
    SELECT 100, 'Out of Space Errors (nospaceerrcnt)', TO_CHAR(NVL(SUM(nospaceerrcnt), 0), '999,999,990') FROM gv$undostat
)
ORDER BY n;

PROMPT
PROMPT === Undo Sizing Recommendation ===
PROMPT

WITH stat AS (
    SELECT
        NVL(MAX(undoblks / NULLIF((end_time - begin_time) * 86400, 0)), 0) AS peak_undo_bps,
        NVL(MAX(maxquerylen), 0) AS longest_query
    FROM gv$undostat
),
param AS (
    SELECT
        TO_NUMBER(p_ret.value) AS undo_retention,
        TO_NUMBER(p_bs.value) AS block_size
    FROM v$parameter p_ret
    CROSS JOIN v$parameter p_bs
    WHERE p_ret.name = 'undo_retention'
      AND p_bs.name = 'db_block_size'
),
current_sz AS (
    SELECT NVL(SUM(f.bytes) / 1024 / 1024, 0) AS cur_mb
    FROM dba_tablespaces t
    JOIN dba_data_files f ON t.tablespace_name = f.tablespace_name
    WHERE t.contents = 'UNDO'
)
SELECT
    ROUND(current_sz.cur_mb, 1) AS current_undo_mb,
    ROUND((stat.peak_undo_bps * GREATEST(param.undo_retention, stat.longest_query) * param.block_size) / 1024 / 1024 * 1.15, 1) AS rec_undo_mb,
    CASE
        WHEN current_sz.cur_mb >= (stat.peak_undo_bps * GREATEST(param.undo_retention, stat.longest_query) * param.block_size) / 1024 / 1024 * 1.15
            THEN 'ADEQUATELY SIZED'
        ELSE 'SPACE EXPANSION RECOMMENDED'
    END AS rec_status
FROM stat, param, current_sz;

PROMPT
PROMPT === Recent Undo Statistics Intervals (GV$UNDOSTAT) ===
PROMPT

SELECT
    inst_id,
    TO_CHAR(begin_time, 'YYYY-MM-DD HH24:MI:SS') AS begin_time,
    TO_CHAR(end_time, 'YYYY-MM-DD HH24:MI:SS') AS end_time,
    undoblks,
    txncount,
    maxquerylen,
    tuned_undoretention,
    unxpstealcnt,
    expstealcnt,
    ssolderrcnt,
    nospaceerrcnt
FROM (
    SELECT
        inst_id,
        begin_time,
        end_time,
        undoblks,
        txncount,
        maxquerylen,
        tuned_undoretention,
        unxpstealcnt,
        expstealcnt,
        ssolderrcnt,
        nospaceerrcnt
    FROM gv$undostat
    ORDER BY begin_time DESC, inst_id
)
WHERE ROWNUM <= 24;

COLUMN inst_id CLEAR
COLUMN parameter CLEAR
COLUMN param_value CLEAR
COLUMN tablespace_name CLEAR
COLUMN retention CLEAR
COLUMN total_mb CLEAR
COLUMN autoextensible CLEAR
COLUMN status CLEAR
COLUMN extent_mb CLEAR
COLUMN extent_count CLEAR
COLUMN metric CLEAR
COLUMN metric_value CLEAR
COLUMN begin_time CLEAR
COLUMN end_time CLEAR
COLUMN undoblks CLEAR
COLUMN txncount CLEAR
COLUMN maxquerylen CLEAR
COLUMN tuned_undoretention CLEAR
COLUMN unxpstealcnt CLEAR
COLUMN expstealcnt CLEAR
COLUMN ssolderrcnt CLEAR
COLUMN nospaceerrcnt CLEAR
COLUMN rec_undo_mb CLEAR
COLUMN current_undo_mb CLEAR
COLUMN rec_status CLEAR

SET FEEDBACK ON
SET VERIFY ON
