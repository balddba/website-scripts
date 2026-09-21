/*******************************************************************************
*
* Script Name: dg_gap_details.sql
* Title: Data Guard Archive Gap Details
* Tags: Data Guard, High Availability, Archive Logs
* Purpose: Identifies archive log sequence gaps between primary and standby databases from v$archive_gap.
*
* Description:
*   Identifies missing archived log sequences and transport/apply gaps on
*   Data Guard standby databases. Queries V$ARCHIVE_GAP for low and high
*   sequence gaps per thread, checks GV$ARCHIVE_DEST_STATUS for gap status
*   and destination errors, and evaluates recent sequence discrepancies from
*   V$ARCHIVED_LOG.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$DATABASE
*   - SELECT on V$ARCHIVE_GAP
*   - SELECT on GV$ARCHIVE_DEST_STATUS
*   - SELECT on V$ARCHIVED_LOG
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Database role, open mode, and Data Guard status
*   - Active archive gap ranges by thread (V$ARCHIVE_GAP)
*   - Archive destination gap statuses and sequence differences (GV$ARCHIVE_DEST_STATUS)
*   - Thread archive and applied sequence summary (V$ARCHIVED_LOG)
*
* Example Usage:
*   sqlplus user/password@yourdb @dg_gap_details.sql
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
COLUMN switchover_status  FORMAT A20             HEADING 'Switchover Status'
COLUMN thread#            FORMAT 9990            HEADING 'Thr'
COLUMN low_sequence#      FORMAT 999999990       HEADING 'Low Missing Seq'
COLUMN high_sequence#     FORMAT 999999990       HEADING 'High Missing Seq'
COLUMN gap_count          FORMAT 999999990       HEADING 'Missing Logs'
COLUMN inst_id            FORMAT 9990            HEADING 'Inst'
COLUMN dest_id            FORMAT 9990            HEADING 'Dest'
COLUMN dest_name          FORMAT A16             HEADING 'Dest Name'
COLUMN dest_type          FORMAT A12             HEADING 'Type'
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
PROMPT Data Guard Archive Gap Details
PROMPT ===============================================================================

PROMPT
PROMPT === Database Role & Status ===
PROMPT

SELECT
    name AS db_name,
    db_unique_name,
    database_role,
    open_mode,
    switchover_status
FROM v$database;

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
PROMPT === Archive Destination Gap Status (GV$ARCHIVE_DEST_STATUS) ===
PROMPT

SELECT
    inst_id,
    dest_id,
    dest_name,
    type AS dest_type,
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
COLUMN switchover_status CLEAR
COLUMN thread# CLEAR
COLUMN low_sequence# CLEAR
COLUMN high_sequence# CLEAR
COLUMN gap_count CLEAR
COLUMN inst_id CLEAR
COLUMN dest_id CLEAR
COLUMN dest_name CLEAR
COLUMN dest_type CLEAR
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
