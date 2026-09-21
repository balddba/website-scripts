/*******************************************************************************
*
* Script Name: dg_apply_lag.sql
* Title: Data Guard Apply and Lag Status
* Tags: Data Guard, High Availability, Replication
* Purpose: Data Guard redo apply progress, transport lag, and MRP process status from v$dataguard_stats and gv$dataguard_process.
*
* Description:
*   Reports real-time Data Guard metrics including transport lag, apply lag,
*   apply finish time, and estimated startup time from V$DATAGUARD_STATS.
*   Shows active Data Guard recovery and transport background processes
*   (MRP0, RFS, PR00, etc.) from GV$DATAGUARD_PROCESS and GV$MANAGED_STANDBY.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$DATABASE
*   - SELECT on V$DATAGUARD_STATS
*   - SELECT on GV$DATAGUARD_PROCESS
*   - SELECT on GV$MANAGED_STANDBY
*   - SELECT on GV$ARCHIVE_DEST_STATUS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Database role, open mode, and protection configuration
*   - Real-time Data Guard lag statistics (V$DATAGUARD_STATS)
*   - Data Guard background process activity and current apply block (GV$DATAGUARD_PROCESS)
*   - Managed standby process state and client thread/sequence tracking (GV$MANAGED_STANDBY)
*   - Archive destination synchronization and gap status (GV$ARCHIVE_DEST_STATUS)
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
COLUMN group#             FORMAT 9990            HEADING 'Grp'
COLUMN thread#            FORMAT 9990            HEADING 'Thr'
COLUMN sequence#          FORMAT 999999990       HEADING 'Sequence#'
COLUMN block#             FORMAT 999999990       HEADING 'Block#'
COLUMN client_process     FORMAT A12             HEADING 'Client Proc'
COLUMN dest_id            FORMAT 9990            HEADING 'Dest'
COLUMN dest_name          FORMAT A16             HEADING 'Dest Name'
COLUMN dest_type          FORMAT A12             HEADING 'Type'
COLUMN dest_status        FORMAT A10             HEADING 'Status'
COLUMN synchronized       FORMAT A8              HEADING 'Sync'
COLUMN gap_status         FORMAT A15             HEADING 'Gap Status'
COLUMN archived_seq#      FORMAT 999999990       HEADING 'Arch Seq'
COLUMN applied_seq#       FORMAT 999999990       HEADING 'Appl Seq'

PROMPT
PROMPT ===============================================================================
PROMPT Data Guard Apply and Lag Status
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
    applied_seq#
FROM gv$archive_dest_status
WHERE status != 'INACTIVE'
ORDER BY inst_id, dest_id;

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
COLUMN group# CLEAR
COLUMN thread# CLEAR
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

SET FEEDBACK ON
SET VERIFY ON
