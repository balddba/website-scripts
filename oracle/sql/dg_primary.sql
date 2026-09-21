/*******************************************************************************
*
* Script Name: dg_primary.sql
* Title: Data Guard primary snapshot
* Tags: Data Guard, Primary, Diagnostics
* Purpose: Print primary-side Data Guard identity, redo, files, and transport status for comparison with each standby
*
* Description:
*   Run this on the primary and dg_standby.sql on each standby, spool both
*   outputs, and compare. The comparison fingerprint, datafile inventory
*   (file#, size, status), redo log sizes, incarnation, and DBID must match.
*   db_unique_name, role, host, paths, SCN, and sequence will differ. Uses
*   V$/GV$ views so it works from CDB$ROOT. On a CDB, run it in the root.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$DATABASE, V$INSTANCE, GV$INSTANCE
*   - SELECT on V$DATABASE_INCARNATION, V$NLS_PARAMETERS, V$TIMEZONE_FILE
*   - SELECT on V$PARAMETER, V$THREAD, V$LOG, V$LOGFILE, V$STANDBY_LOG
*   - SELECT on V$DATAFILE, V$TEMPFILE, V$TABLESPACE, V$CONTROLFILE
*   - SELECT on GV$ARCHIVE_DEST, GV$ARCHIVE_DEST_STATUS, V$ARCHIVED_LOG
*   - SELECT on V$DATAGUARD_CONFIG, V$DATAGUARD_STATUS, V$DATAGUARD_STATS
*   - SELECT on GV$MANAGED_STANDBY, GV$DATAGUARD_PROCESS
*   - SELECT on GV$PDBS, V$FLASHBACK_DATABASE_LOG
*
* Output Format:
*   - Role check and comparison fingerprint (name/value)
*   - Instances, protection, incarnation, NLS, parameters
*   - Archive destinations and transport status
*   - Online and standby redo logs, datafiles, tempfiles, PDBs
*   - Shipping summary and recent Data Guard messages
*
* Example Usage:
*   SQL> SPOOL dg_primary.txt
*   SQL> @dg_primary.sql
*   SQL> SPOOL OFF
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET ECHO OFF
SET VERIFY OFF
SET FEEDBACK ON
SET HEADING ON
SET LINESIZE 240
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF
SET WRAP ON
SET NULL '(null)'

ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';

COLUMN role_check FORMAT A60
COLUMN open_mode_check FORMAT A60
COLUMN metric FORMAT A32 HEADING 'Metric'
COLUMN value FORMAT A100 HEADING 'Value'
COLUMN inst_id FORMAT 9990 HEADING 'Inst'
COLUMN instance_name FORMAT A16
COLUMN host_name FORMAT A30
COLUMN version FORMAT A17
COLUMN status FORMAT A16
COLUMN instance_role FORMAT A18
COLUMN startup_time FORMAT A19
COLUMN thread# FORMAT 9990 HEADING 'Thr'
COLUMN database_role FORMAT A18
COLUMN open_mode FORMAT A22
COLUMN protection_mode FORMAT A22
COLUMN protection_level FORMAT A22
COLUMN switchover_status FORMAT A20
COLUMN force_logging FORMAT A16
COLUMN flashback_on FORMAT A12
COLUMN dataguard_broker FORMAT A10 HEADING 'Broker'
COLUMN db_unique_name FORMAT A30
COLUMN dest_role FORMAT A18
COLUMN parent_dbun FORMAT A30
COLUMN incarnation# FORMAT 9999990 HEADING 'Incarn'
COLUMN resetlogs_time FORMAT A19
COLUMN resetlogs_change# FORMAT 999999999999999 HEADING 'Resetlogs SCN'
COLUMN parameter FORMAT A32
COLUMN param_name FORMAT A36 HEADING 'Name'
COLUMN param_value FORMAT A120 HEADING 'Value'
COLUMN dest_id FORMAT 9990 HEADING 'Dest'
COLUMN target FORMAT A10
COLUMN destination FORMAT A60
COLUMN valid_role FORMAT A12
COLUMN valid_type FORMAT A12
COLUMN transmit_mode FORMAT A12
COLUMN affirm FORMAT A8
COLUMN delay_mins FORMAT 99990 HEADING 'Delay'
COLUMN error FORMAT A60
COLUMN dest_name FORMAT A20
COLUMN database_mode FORMAT A16
COLUMN recovery_mode FORMAT A28
COLUMN synchronized FORMAT A8 HEADING 'Sync'
COLUMN gap_status FORMAT A16
COLUMN archived_seq# FORMAT 999999990 HEADING 'Arch Seq'
COLUMN applied_seq# FORMAT 999999990 HEADING 'Appl Seq'
COLUMN group# FORMAT 9990 HEADING 'Grp'
COLUMN sequence# FORMAT 999999990 HEADING 'Seq'
COLUMN size_mb FORMAT 999,999,990 HEADING 'MB'
COLUMN blocksize FORMAT 99990
COLUMN members FORMAT 9990
COLUMN archived FORMAT A8
COLUMN used FORMAT 999999990
COLUMN type FORMAT A16
COLUMN member FORMAT A80
COLUMN enabled FORMAT A12
COLUMN groups FORMAT 9990
COLUMN instance FORMAT A16
COLUMN checkpoint_change# FORMAT 999999999999999 HEADING 'Ckpt SCN'
COLUMN is_recovery_dest_file FORMAT A8 HEADING 'FRA'
COLUMN controlfile_name FORMAT A80 HEADING 'Name'
COLUMN ts# FORMAT 9990
COLUMN tablespace_name FORMAT A30
COLUMN bigfile FORMAT A8
COLUMN file_count FORMAT 9990 HEADING 'Files'
COLUMN size_gb FORMAT 999,999,990.00 HEADING 'GB'
COLUMN file# FORMAT 99990
COLUMN file_name FORMAT A80
COLUMN con_id FORMAT 9990 HEADING 'Con'
COLUMN pdb_name FORMAT A30
COLUMN restricted FORMAT A10
COLUMN open_time FORMAT A19
COLUMN process FORMAT A12
COLUMN pid FORMAT 999999990
COLUMN client_process FORMAT A12
COLUMN dg_name FORMAT A12 HEADING 'Name'
COLUMN dg_role FORMAT A16 HEADING 'Role'
COLUMN dg_status FORMAT A16 HEADING 'Status'
COLUMN last_archived_seq FORMAT 999999990 HEADING 'Last Arch'
COLUMN last_applied_seq FORMAT 999999990 HEADING 'Last Appl'
COLUMN last_next_time FORMAT A19 HEADING 'Last Time'
COLUMN ts FORMAT A19 HEADING 'Timestamp'
COLUMN severity FORMAT A12
COLUMN message FORMAT A140
COLUMN oldest_flashback_time FORMAT A19
COLUMN retention_target FORMAT 999999990
COLUMN flashback_size_gb FORMAT 999,999,990.00

PROMPT
PROMPT ===============================================================================
PROMPT Data Guard primary snapshot
PROMPT ===============================================================================

PROMPT
PROMPT Role check
PROMPT ==========

SELECT
    CASE
        WHEN database_role = 'PRIMARY' THEN 'OK'
        ELSE 'WARNING: expected PRIMARY, found ' || database_role
    END AS role_check,
    CASE
        WHEN open_mode = 'READ WRITE' THEN 'OK'
        ELSE 'WARNING: expected READ WRITE, found ' || open_mode
    END AS open_mode_check
FROM v$database;

PROMPT
PROMPT Comparison fingerprint
PROMPT ======================
PROMPT Compare this block with dg_standby.sql. DBID, name, resetlogs, compatible,
PROMPT block size, charset, file counts, file# checksum, and redo sizes must match.

SELECT metric, value
FROM (
    SELECT 10 AS n, 'collected_at' AS metric, TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS') AS value FROM dual
    UNION ALL
    SELECT 20, 'host_name', host_name FROM v$instance
    UNION ALL
    SELECT 30, 'instance_name', instance_name FROM v$instance
    UNION ALL
    SELECT 40, 'instance_status', status FROM v$instance
    UNION ALL
    SELECT 50, 'version', version FROM v$instance
    UNION ALL
    SELECT 60, 'startup_time', TO_CHAR(startup_time, 'YYYY-MM-DD HH24:MI:SS') FROM v$instance
    UNION ALL
    SELECT 70, 'thread#', TO_CHAR(thread#) FROM v$instance
    UNION ALL
    SELECT 80, 'dbid', TO_CHAR(dbid) FROM v$database
    UNION ALL
    SELECT 90, 'name', name FROM v$database
    UNION ALL
    SELECT 100, 'db_unique_name', db_unique_name FROM v$database
    UNION ALL
    SELECT 110, 'database_role', database_role FROM v$database
    UNION ALL
    SELECT 120, 'open_mode', open_mode FROM v$database
    UNION ALL
    SELECT 130, 'log_mode', log_mode FROM v$database
    UNION ALL
    SELECT 140, 'cdb', cdb FROM v$database
    UNION ALL
    SELECT 150, 'platform_name', platform_name FROM v$database
    UNION ALL
    SELECT 160, 'created', TO_CHAR(created, 'YYYY-MM-DD HH24:MI:SS') FROM v$database
    UNION ALL
    SELECT 170, 'resetlogs_time', TO_CHAR(resetlogs_time, 'YYYY-MM-DD HH24:MI:SS') FROM v$database
    UNION ALL
    SELECT 180, 'resetlogs_change#', TO_CHAR(resetlogs_change#) FROM v$database
    UNION ALL
    SELECT 190, 'current_scn', TO_CHAR(current_scn) FROM v$database
    UNION ALL
    SELECT 200, 'controlfile_type', controlfile_type FROM v$database
    UNION ALL
    SELECT 210, 'controlfile_change#', TO_CHAR(controlfile_change#) FROM v$database
    UNION ALL
    SELECT 220, 'controlfile_time', TO_CHAR(controlfile_time, 'YYYY-MM-DD HH24:MI:SS') FROM v$database
    UNION ALL
    SELECT 230, 'incarnation#', TO_CHAR(incarnation#)
    FROM v$database_incarnation
    WHERE status = 'CURRENT'
    UNION ALL
    SELECT 240, 'force_logging', force_logging FROM v$database
    UNION ALL
    SELECT 250, 'flashback_on', flashback_on FROM v$database
    UNION ALL
    SELECT 260, 'dataguard_broker', dataguard_broker FROM v$database
    UNION ALL
    SELECT 270, 'protection_mode', protection_mode FROM v$database
    UNION ALL
    SELECT 280, 'protection_level', protection_level FROM v$database
    UNION ALL
    SELECT 290, 'switchover_status', switchover_status FROM v$database
    UNION ALL
    SELECT 300, 'guard_status', guard_status FROM v$database
    UNION ALL
    SELECT 310, 'supplemental_log_min', supplemental_log_data_min FROM v$database
    UNION ALL
    SELECT 320, 'supplemental_log_pk', supplemental_log_data_pk FROM v$database
    UNION ALL
    SELECT 330, 'supplemental_log_ui', supplemental_log_data_ui FROM v$database
    UNION ALL
    SELECT 340, 'supplemental_log_fk', supplemental_log_data_fk FROM v$database
    UNION ALL
    SELECT 350, 'supplemental_log_all', supplemental_log_data_all FROM v$database
    UNION ALL
    SELECT 360, 'fs_failover_status', fs_failover_status FROM v$database
    UNION ALL
    SELECT 370, 'fs_failover_target', fs_failover_current_target FROM v$database
    UNION ALL
    SELECT 380, 'fs_failover_observer', fs_failover_observer_present FROM v$database
    UNION ALL
    SELECT 390, 'primary_db_unique_name', primary_db_unique_name FROM v$database
    UNION ALL
    SELECT 400, 'compatible', value FROM v$parameter WHERE name = 'compatible'
    UNION ALL
    SELECT 410, 'db_block_size', value FROM v$parameter WHERE name = 'db_block_size'
    UNION ALL
    SELECT 420, 'cluster_database', value FROM v$parameter WHERE name = 'cluster_database'
    UNION ALL
    SELECT 430, 'remote_login_passwordfile', value FROM v$parameter WHERE name = 'remote_login_passwordfile'
    UNION ALL
    SELECT 440, 'standby_file_management', value FROM v$parameter WHERE name = 'standby_file_management'
    UNION ALL
    SELECT 450, 'log_archive_config', value FROM v$parameter WHERE name = 'log_archive_config'
    UNION ALL
    SELECT 460, 'fal_server', value FROM v$parameter WHERE name = 'fal_server'
    UNION ALL
    SELECT 470, 'fal_client', value FROM v$parameter WHERE name = 'fal_client'
    UNION ALL
    SELECT 480, 'dg_broker_start', value FROM v$parameter WHERE name = 'dg_broker_start'
    UNION ALL
    SELECT 490, 'nls_characterset', value FROM v$nls_parameters WHERE parameter = 'NLS_CHARACTERSET'
    UNION ALL
    SELECT 500, 'nls_nchar_characterset', value FROM v$nls_parameters WHERE parameter = 'NLS_NCHAR_CHARACTERSET'
    UNION ALL
    SELECT 510, 'nls_length_semantics', value FROM v$nls_parameters WHERE parameter = 'NLS_LENGTH_SEMANTICS'
    UNION ALL
    SELECT 520, 'timezone_file', filename FROM v$timezone_file
    UNION ALL
    SELECT 530, 'timezone_version', TO_CHAR(version) FROM v$timezone_file
    UNION ALL
    SELECT 540, 'datafile_count', TO_CHAR(COUNT(*)) FROM v$datafile
    UNION ALL
    SELECT 550, 'datafile_total_gb', TO_CHAR(ROUND(SUM(bytes) / 1024 / 1024 / 1024, 2)) FROM v$datafile
    UNION ALL
    SELECT 560, 'datafile_bytes_sum', TO_CHAR(SUM(bytes)) FROM v$datafile
    UNION ALL
    SELECT 570, 'datafile_file#_sum', TO_CHAR(SUM(file#)) FROM v$datafile
    UNION ALL
    SELECT 580, 'datafile_max_checkpoint_scn', TO_CHAR(MAX(checkpoint_change#)) FROM v$datafile
    UNION ALL
    SELECT 590, 'tempfile_count', TO_CHAR(COUNT(*)) FROM v$tempfile
    UNION ALL
    SELECT 600, 'tempfile_total_gb', TO_CHAR(ROUND(NVL(SUM(bytes), 0) / 1024 / 1024 / 1024, 2)) FROM v$tempfile
    UNION ALL
    SELECT 610, 'orl_groups', TO_CHAR(COUNT(*)) FROM v$log
    UNION ALL
    SELECT 620, 'orl_size_mb', (
        SELECT LISTAGG(size_mb, ',') WITHIN GROUP (ORDER BY size_mb)
        FROM (SELECT DISTINCT ROUND(bytes / 1024 / 1024) AS size_mb FROM v$log)
    ) FROM dual
    UNION ALL
    SELECT 630, 'srl_groups', TO_CHAR(COUNT(*)) FROM v$standby_log
    UNION ALL
    SELECT 640, 'srl_size_mb', (
        SELECT LISTAGG(size_mb, ',') WITHIN GROUP (ORDER BY size_mb)
        FROM (SELECT DISTINCT ROUND(bytes / 1024 / 1024) AS size_mb FROM v$standby_log)
    ) FROM dual
    UNION ALL
    SELECT 650, 'log_threads', TO_CHAR(COUNT(DISTINCT thread#)) FROM v$log
)
ORDER BY n;

PROMPT
PROMPT Instances
PROMPT =========

SELECT
    inst_id,
    instance_name,
    host_name,
    version,
    status,
    instance_role,
    thread#,
    startup_time
FROM gv$instance
ORDER BY inst_id;

PROMPT
PROMPT Role and protection
PROMPT ===================

SELECT
    name,
    db_unique_name,
    database_role,
    open_mode,
    protection_mode,
    protection_level,
    switchover_status,
    force_logging,
    flashback_on,
    dataguard_broker
FROM v$database;

PROMPT
PROMPT Incarnations
PROMPT ============

SELECT
    incarnation#,
    status,
    resetlogs_time,
    resetlogs_change#,
    prior_incarnation#
FROM v$database_incarnation
ORDER BY incarnation#;

PROMPT
PROMPT NLS and timezone
PROMPT ================

SELECT parameter, value
FROM v$nls_parameters
WHERE parameter IN (
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET',
    'NLS_LENGTH_SEMANTICS'
)
ORDER BY parameter;

SELECT filename AS timezone_file, version AS timezone_version
FROM v$timezone_file;

PROMPT
PROMPT Data Guard configuration
PROMPT ========================

SELECT db_unique_name, parent_dbun, dest_role
FROM v$dataguard_config
ORDER BY db_unique_name;

PROMPT
PROMPT Key parameters
PROMPT ==============

SELECT name AS param_name, value AS param_value
FROM v$parameter
WHERE name IN (
        'compatible',
        'db_name',
        'db_unique_name',
        'db_domain',
        'db_block_size',
        'db_files',
        'cluster_database',
        'enable_pluggable_database',
        'undo_management',
        'undo_tablespace',
        'undo_retention',
        'remote_login_passwordfile',
        'fal_server',
        'fal_client',
        'standby_file_management',
        'db_file_name_convert',
        'log_file_name_convert',
        'log_archive_config',
        'log_archive_format',
        'log_archive_max_processes',
        'log_archive_min_succeed_dest',
        'archive_lag_target',
        'dg_broker_start',
        'dg_broker_config_file1',
        'dg_broker_config_file2',
        'db_recovery_file_dest',
        'db_recovery_file_dest_size',
        'db_create_file_dest',
        'control_files',
        'spfile',
        'processes',
        'open_cursors',
        'sga_target',
        'pga_aggregate_target',
        'memory_target',
        'use_large_pages',
        'max_string_size',
        'local_undo_enabled',
        'optimizer_features_enable',
        'db_lost_write_protect'
    )
   OR (name LIKE 'log_archive_dest_%' AND value IS NOT NULL)
   OR (name LIKE 'db_create_online_log_dest_%' AND value IS NOT NULL)
ORDER BY name;

PROMPT
PROMPT Archive destinations
PROMPT ====================

SELECT
    inst_id,
    dest_id,
    status,
    target,
    db_unique_name,
    valid_role,
    valid_type,
    transmit_mode,
    affirm,
    delay_mins,
    destination,
    error
FROM gv$archive_dest
WHERE destination IS NOT NULL
ORDER BY inst_id, dest_id;

PROMPT
PROMPT Archive destination status
PROMPT ==========================
PROMPT On the primary, APPL SEQ is the last sequence applied on that standby.

SELECT
    inst_id,
    dest_id,
    dest_name,
    status,
    type,
    database_mode,
    recovery_mode,
    protection_mode,
    db_unique_name,
    synchronized,
    gap_status,
    archived_seq#,
    applied_seq#,
    error
FROM gv$archive_dest_status
WHERE status != 'INACTIVE'
ORDER BY inst_id, dest_id;

PROMPT
PROMPT Redo sequence summary
PROMPT =====================

SELECT
    thread#,
    MAX(sequence#) AS last_archived_seq,
    MAX(CASE WHEN applied = 'YES' THEN sequence# END) AS last_applied_seq,
    MAX(next_time) AS last_next_time
FROM v$archived_log
WHERE resetlogs_change# = (SELECT resetlogs_change# FROM v$database)
GROUP BY thread#
ORDER BY thread#;

PROMPT
PROMPT Online redo logs
PROMPT ================

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
PROMPT Standby redo logs
PROMPT =================
PROMPT Primary should have standby redo logs sized at least as large as the
PROMPT online logs so role reversal does not have to add them later.

SELECT
    group#,
    thread#,
    sequence#,
    ROUND(bytes / 1024 / 1024) AS size_mb,
    used,
    archived,
    status
FROM v$standby_log
ORDER BY thread#, group#;

PROMPT
PROMPT Redo log members
PROMPT ================

SELECT group#, type, status, member
FROM v$logfile
ORDER BY type, group#, member;

PROMPT
PROMPT Threads
PROMPT =======

SELECT
    thread#,
    status,
    enabled,
    groups,
    instance,
    sequence#,
    checkpoint_change#
FROM v$thread
ORDER BY thread#;

PROMPT
PROMPT Control files
PROMPT =============

SELECT status, is_recovery_dest_file, name AS controlfile_name
FROM v$controlfile
ORDER BY name;

PROMPT
PROMPT Tablespaces
PROMPT ===========

SELECT
    ts.con_id,
    ts.ts#,
    ts.name AS tablespace_name,
    ts.bigfile,
    COUNT(df.file#) AS file_count,
    ROUND(SUM(df.bytes) / 1024 / 1024 / 1024, 2) AS size_gb
FROM v$tablespace ts
JOIN v$datafile df
    ON df.ts# = ts.ts#
   AND df.con_id = ts.con_id
GROUP BY
    ts.con_id,
    ts.ts#,
    ts.name,
    ts.bigfile
ORDER BY
    ts.con_id,
    ts.ts#;

PROMPT
PROMPT Datafile inventory
PROMPT ==================
PROMPT Compare FILE#, GB, and STATUS with the standby. Names often differ
PROMPT because of db_file_name_convert.

SELECT
    con_id,
    file#,
    status,
    enabled,
    ROUND(bytes / 1024 / 1024 / 1024, 2) AS size_gb,
    checkpoint_change#,
    name AS file_name
FROM v$datafile
ORDER BY con_id, file#;

PROMPT
PROMPT Tempfile inventory
PROMPT ==================
PROMPT Tempfile count and paths can differ on a standby until they are created.

SELECT
    con_id,
    file#,
    status,
    enabled,
    ROUND(bytes / 1024 / 1024 / 1024, 2) AS size_gb,
    name AS file_name
FROM v$tempfile
ORDER BY con_id, file#;

PROMPT
PROMPT Pluggable databases
PROMPT ===================

SELECT
    inst_id,
    con_id,
    name AS pdb_name,
    open_mode,
    restricted,
    TO_CHAR(open_time, 'YYYY-MM-DD HH24:MI:SS') AS open_time
FROM gv$pdbs
ORDER BY con_id, inst_id;

PROMPT
PROMPT Data Guard processes
PROMPT ====================

SELECT
    inst_id,
    name AS dg_name,
    pid,
    role AS dg_role,
    group#,
    thread#,
    sequence#,
    action AS dg_status
FROM gv$dataguard_process
ORDER BY inst_id, name, thread#, group#;

PROMPT
PROMPT Managed standby / transport processes
PROMPT =====================================

SELECT
    inst_id,
    process,
    pid,
    status,
    client_process,
    thread#,
    sequence#,
    delay_mins
FROM gv$managed_standby
ORDER BY inst_id, process, thread#;

PROMPT
PROMPT Redo shipping summary
PROMPT =====================
PROMPT Rows with TYPE = PHYSICAL are standbys this primary is shipping to.
PROMPT GAP_STATUS and ARCH SEQ vs APPL SEQ show transport and apply lag.

SELECT
    inst_id,
    dest_id,
    db_unique_name,
    status,
    type,
    database_mode,
    recovery_mode,
    synchronized,
    gap_status,
    archived_seq#,
    applied_seq#,
    CASE
        WHEN archived_seq# IS NULL OR applied_seq# IS NULL THEN NULL
        ELSE archived_seq# - applied_seq#
    END AS seq_gap,
    error
FROM gv$archive_dest_status
WHERE type IN ('PHYSICAL', 'LOGICAL', 'SNAPSHOT')
ORDER BY inst_id, dest_id;

PROMPT
PROMPT Switchover readiness
PROMPT ====================

SELECT
    switchover_status,
    protection_mode,
    protection_level,
    force_logging,
    CASE
        WHEN force_logging = 'YES' THEN 'OK'
        ELSE 'WARNING: enable FORCE LOGGING before using this primary for Data Guard'
    END AS force_logging_check,
    CASE
        WHEN (SELECT COUNT(*) FROM v$standby_log) = 0
            THEN 'WARNING: no standby redo logs on primary (needed for role reversal)'
        ELSE 'OK: standby redo logs present'
    END AS srl_check
FROM v$database;

PROMPT
PROMPT Flashback
PROMPT =========

SELECT
    oldest_flashback_scn,
    oldest_flashback_time,
    retention_target,
    ROUND(flashback_size / 1024 / 1024 / 1024, 2) AS flashback_size_gb
FROM v$flashback_database_log;

PROMPT
PROMPT Recent Data Guard messages
PROMPT ==========================

SELECT
    TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI:SS') AS ts,
    severity,
    error_code,
    message
FROM (
    SELECT timestamp, severity, error_code, message
    FROM v$dataguard_status
    WHERE timestamp > SYSDATE - 1
    ORDER BY timestamp DESC
)
WHERE ROWNUM <= 25;

PROMPT
PROMPT End of Data Guard primary snapshot
PROMPT
