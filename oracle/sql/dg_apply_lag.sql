/*******************************************************************************
*
* Script Name: dg_apply_lag.sql
* Title: Data Guard Apply Lag and Gap Details
* Tags: Data Guard, High Availability, Replication, Archive Logs
* Purpose: Data Guard redo apply progress, transport lag, archive gaps, and MRP process status.
*
* Description:
*   Reports real-time Data Guard metrics including transport lag, apply lag,
*   apply finish time, and estimated startup time from V$DATAGUARD_STATS.
*   Shows active Data Guard recovery and transport background processes
*   (MRP0, RFS, PR00, etc.) from GV$DATAGUARD_PROCESS and GV$MANAGED_STANDBY.
*   Identifies missing archived log sequences from V$ARCHIVE_GAP, checks
*   archive destination gap status and errors, and summarizes archived versus
*   applied sequences by thread from V$ARCHIVED_LOG.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$DATABASE
*   - SELECT on V$DATAGUARD_STATS
*   - SELECT on V$ARCHIVE_GAP
*   - SELECT on V$ARCHIVED_LOG
*   - SELECT on GV$DATAGUARD_PROCESS
*   - SELECT on GV$MANAGED_STANDBY
*   - SELECT on GV$ARCHIVE_DEST_STATUS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Database role, open mode, and protection configuration
*   - Real-time Data Guard lag statistics (V$DATAGUARD_STATS)
*   - Active archive gap ranges by thread (V$ARCHIVE_GAP)
*   - Data Guard background process activity and current apply block (GV$DATAGUARD_PROCESS)
*   - Managed standby process state and client thread/sequence tracking (GV$MANAGED_STANDBY)
*   - Archive destination synchronization, gap status, sequence difference, and errors (GV$ARCHIVE_DEST_STATUS)
*   - Thread archive and applied sequence summary (V$ARCHIVED_LOG)
*
* Example Usage:
*   sqlplus user/password@yourdb @dg_apply_lag.sql
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
COLUMN db_unique_name     FORMAT A20             HEADING 'DB Unique Name'
COLUMN database_role      FORMAT A16             HEADING 'Role'
COLUMN open_mode          FORMAT A16             HEADING 'Open Mode'
COLUMN protection_mode    FORMAT A20             HEADING 'Protection Mode'
COLUMN switchover_status  FORMAT A20             HEADING 'Switchover Status'
COLUMN metric_name        FORMAT A25             HEADING 'Metric'
COLUMN metric_value       FORMAT A22             HEADING 'Value'
COLUMN unit               FORMAT A12             HEADING 'Unit'
COLUMN time_computed      FORMAT A19             HEADING 'Time Computed'
COLUMN datum_time         FORMAT A19             HEADING 'Datum Time'
COLUMN inst_id            FORMAT 9990            HEADING 'Inst'
COLUMN process_name       FORMAT A12             HEADING 'Process'
COLUMN pid                FORMAT 999999990       HEADING 'PID'
COLUMN role               FORMAT A16             HEADING 'Process Role'
COLUMN action             FORMAT A22             HEADING 'Action / Status'
COLUMN status             FORMAT A18             HEADING 'Status'
COLUMN group#             FORMAT 9990            HEADING 'Grp'
COLUMN thread#            FORMAT 9990            HEADING 'Thr'
COLUMN low_sequence#      FORMAT 999999990       HEADING 'Low Missing Seq'
COLUMN high_sequence#     FORMAT 999999990       HEADING 'High Missing Seq'
COLUMN gap_count          FORMAT 999999990       HEADING 'Missing Logs'
COLUMN sequence#          FORMAT 999999990       HEADING 'Sequence#'
COLUMN block#             FORMAT 999999990       HEADING 'Block#'
COLUMN client_process     FORMAT A12             HEADING 'Client Proc'
COLUMN dest_id            FORMAT 9990            HEADING 'Dest'
COLUMN dest_name          FORMAT A16             HEADING 'Dest Name'
COLUMN dest_type          FORMAT A12             HEADING 'Type'
COLUMN dest_status        FORMAT A10             HEADING 'Status'
COLUMN synchronized       FORMAT A8              HEADING 'Sync'
COLUMN gap_status         FORMAT A18             HEADING 'Gap Status'
COLUMN archived_seq#      FORMAT 999999990       HEADING 'Arch Seq'
COLUMN applied_seq#       FORMAT 999999990       HEADING 'Appl Seq'
COLUMN seq_diff           FORMAT 999999990       HEADING 'Seq Diff'
COLUMN error              FORMAT A40 TRUNC       HEADING 'Error'
COLUMN max_arch_seq       FORMAT 999999990       HEADING 'Max Arch Seq'
COLUMN max_appl_seq       FORMAT 999999990       HEADING 'Max Appl Seq'
COLUMN last_applied_time  FORMAT A19             HEADING 'Last Applied Time'

PROMPT
PROMPT ===============================================================================
PROMPT Data Guard Apply Lag and Gap Details
PROMPT ===============================================================================

PROMPT
PROMPT === Database Role & Protection ===
PROMPT

SELECT
    name AS db_name,
    db_unique_name,
    database_role,
    open_mode,
    protection_mode,
    switchover_status
FROM v$database;

PROMPT
PROMPT === Data Guard Lag Statistics (V$DATAGUARD_STATS) ===
PROMPT

SELECT
    name AS metric_name,
    value AS metric_value,
    unit,
    time_computed,
    datum_time
FROM v$dataguard_stats
ORDER BY name;

PROMPT
PROMPT === Active Archive Gaps (V$ARCHIVE_GAP) ===
PROMPT

SELECT
    thread#,
    low_sequence#,
    high_sequence#,
    (high_sequence# - low_sequence# + 1) AS gap_count
FROM v$archive_gap
ORDER BY thread#, low_sequence#;

PROMPT
PROMPT === Data Guard Processes (GV$DATAGUARD_PROCESS) ===
PROMPT

SELECT
    inst_id,
    name AS process_name,
    pid,
    role,
    action,
    group#,
    thread#,
    sequence#,
    block#
FROM gv$dataguard_process
ORDER BY inst_id, name, thread#;

PROMPT
PROMPT === Managed Standby Recovery Processes (GV$MANAGED_STANDBY) ===
PROMPT

SELECT
    inst_id,
    process AS process_name,
    pid,
    status,
    client_process,
    thread#,
    sequence#,
    block#
FROM gv$managed_standby
ORDER BY inst_id, process, thread#;

PROMPT
PROMPT === Archive Destination Status & Synchronization ===
PROMPT

SELECT
    inst_id,
    dest_id,
    dest_name,
    type AS dest_type,
    status AS dest_status,
    synchronized,
    gap_status,
    archived_seq#,
    applied_seq#,
    CASE
        WHEN archived_seq# IS NULL OR applied_seq# IS NULL THEN NULL
        ELSE archived_seq# - applied_seq#
    END AS seq_diff,
    error
FROM gv$archive_dest_status
WHERE status != 'INACTIVE'
ORDER BY inst_id, dest_id;

PROMPT
PROMPT === Thread Archive & Applied Sequence Summary (V$ARCHIVED_LOG) ===
PROMPT

SELECT
    thread#,
    MAX(sequence#) AS max_arch_seq,
    MAX(CASE WHEN applied = 'YES' THEN sequence# END) AS max_appl_seq,
    MAX(sequence#) - NVL(MAX(CASE WHEN applied = 'YES' THEN sequence# END), 0) AS seq_diff,
    TO_CHAR(MAX(CASE WHEN applied = 'YES' THEN next_time END), 'YYYY-MM-DD HH24:MI:SS') AS last_applied_time
FROM v$archived_log
WHERE resetlogs_change# = (SELECT resetlogs_change# FROM v$database)
GROUP BY thread#
ORDER BY thread#;

COLUMN db_name CLEAR
COLUMN db_unique_name CLEAR
COLUMN database_role CLEAR
COLUMN open_mode CLEAR
COLUMN protection_mode CLEAR
COLUMN switchover_status CLEAR
COLUMN metric_name CLEAR
COLUMN metric_value CLEAR
COLUMN unit CLEAR
COLUMN time_computed CLEAR
COLUMN datum_time CLEAR
COLUMN inst_id CLEAR
COLUMN process_name CLEAR
COLUMN pid CLEAR
COLUMN role CLEAR
COLUMN action CLEAR
COLUMN status CLEAR
COLUMN group# CLEAR
COLUMN thread# CLEAR
COLUMN low_sequence# CLEAR
COLUMN high_sequence# CLEAR
COLUMN gap_count CLEAR
COLUMN sequence# CLEAR
COLUMN block# CLEAR
COLUMN client_process CLEAR
COLUMN dest_id CLEAR
COLUMN dest_name CLEAR
COLUMN dest_type CLEAR
COLUMN dest_status CLEAR
COLUMN synchronized CLEAR
COLUMN gap_status CLEAR
COLUMN archived_seq# CLEAR
COLUMN applied_seq# CLEAR
COLUMN seq_diff CLEAR
COLUMN error CLEAR
COLUMN max_arch_seq CLEAR
COLUMN max_appl_seq CLEAR
COLUMN last_applied_time CLEAR

SET FEEDBACK ON
SET VERIFY ON
