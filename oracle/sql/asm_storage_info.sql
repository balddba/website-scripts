/*******************************************************************************
*
* Script Name: asm_storage_info.sql
* Title: ASM storage information
* Tags: ASM, Storage, Capacity
* Purpose: Display Oracle ASM disk group capacity, disk status, clients, and operations
*
* Description:
*   Provides a SQL*Plus report for Oracle Automatic Storage Management (ASM)
*   storage. It summarizes ASM instance details, disk group capacity and usable
*   space, member disk status, connected clients, and currently running ASM
*   operations.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$INSTANCE
*   - SELECT on V$ASM_DISKGROUP
*   - SELECT on V$ASM_DISK
*   - SELECT on V$ASM_CLIENT
*   - SELECT on V$ASM_OPERATION
*
* Output Format:
*   - ASM instance name, host, version, and status
*   - Disk group state, redundancy, total/free/usable space, and percent used
*   - Disk group compatibility and offline disk count
*   - ASM disk mount/header/mode/state, fail group, path, and capacity
*   - ASM client database or instance connections
*   - Active ASM rebalance or other operations
*
* Example Usage:
*   sqlplus / as sysasm @asm_storage_info.sql
*   sqlplus user/password@+ASM @asm_storage_info.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET LINESIZE 240
SET PAGESIZE 100
SET VERIFY OFF
SET FEEDBACK ON
SET TRIMSPOOL ON
SET TAB OFF

COLUMN instance_name FORMAT A16
COLUMN host_name FORMAT A30
COLUMN version FORMAT A14
COLUMN status FORMAT A10

COLUMN diskgroup_name FORMAT A24 HEADING 'Disk Group'
COLUMN state FORMAT A12
COLUMN redundancy FORMAT A12
COLUMN total_gb FORMAT 999,999,990.0 HEADING 'Total GB'
COLUMN free_gb FORMAT 999,999,990.0 HEADING 'Free GB'
COLUMN usable_file_gb FORMAT 999,999,990.0
COLUMN required_mirror_free_gb FORMAT 999,999,990.0
COLUMN pct_used FORMAT 990.0
COLUMN offline_disks FORMAT 999,990
COLUMN compatibility FORMAT A14
COLUMN database_compatibility FORMAT A14

COLUMN disk_number FORMAT 9990 HEADING 'Disk#'
COLUMN disk_name FORMAT A24 TRUNC HEADING 'Disk Name'
COLUMN failgroup FORMAT A20 TRUNC HEADING 'Fail Group'
COLUMN mount_status FORMAT A8 HEADING 'Mount'
COLUMN header_status FORMAT A12 HEADING 'Header'
COLUMN mode_status FORMAT A7 HEADING 'Mode'
COLUMN disk_state FORMAT A8 HEADING 'State'
COLUMN path FORMAT A50 TRUNC HEADING 'Path'

COLUMN db_name FORMAT A12
COLUMN client_instance FORMAT A18
COLUMN software_version FORMAT A16
COLUMN compatible_version FORMAT A16

COLUMN operation FORMAT A12
COLUMN pass FORMAT A12
COLUMN power FORMAT 9990
COLUMN actual FORMAT 9990
COLUMN sofar FORMAT 999,999,990
COLUMN est_work FORMAT 999,999,990
COLUMN est_minutes FORMAT 999,990.0
COLUMN error_code FORMAT A12

PROMPT
PROMPT ASM instance
PROMPT ============

SELECT
    instance_name,
    host_name,
    version,
    status
FROM v$instance;

PROMPT
PROMPT ASM disk groups
PROMPT ===============

SELECT
    name AS diskgroup_name,
    state,
    type AS redundancy,
    ROUND(total_mb / 1024, 1) AS total_gb,
    ROUND(free_mb / 1024, 1) AS free_gb,
    ROUND(usable_file_mb / 1024, 1) AS usable_file_gb,
    ROUND(required_mirror_free_mb / 1024, 1) AS required_mirror_free_gb,
    ROUND((total_mb - free_mb) / NULLIF(total_mb, 0) * 100, 1) AS pct_used,
    offline_disks,
    compatibility,
    database_compatibility
FROM v$asm_diskgroup
ORDER BY name;

PROMPT
PROMPT ASM disks
PROMPT =========

SELECT
    dg.name AS diskgroup_name,
    d.disk_number,
    d.name AS disk_name,
    d.failgroup,
    d.mount_status,
    d.header_status,
    d.mode_status,
    d.state AS disk_state,
    ROUND(d.total_mb / 1024, 1) AS total_gb,
    ROUND(d.free_mb / 1024, 1) AS free_gb,
    d.path
FROM v$asm_disk d
LEFT JOIN v$asm_diskgroup dg
    ON dg.group_number = d.group_number
ORDER BY
    dg.name,
    d.failgroup,
    d.disk_number;

PROMPT
PROMPT ASM clients
PROMPT ===========

SELECT
    dg.name AS diskgroup_name,
    c.instance_name AS client_instance,
    c.db_name,
    c.status,
    c.software_version,
    c.compatible_version
FROM v$asm_client c
LEFT JOIN v$asm_diskgroup dg
    ON dg.group_number = c.group_number
ORDER BY
    dg.name,
    c.instance_name,
    c.db_name;

PROMPT
PROMPT Active ASM operations
PROMPT =====================

SELECT
    dg.name AS diskgroup_name,
    o.operation,
    o.state,
    o.power,
    o.actual,
    o.sofar,
    o.est_work,
    ROUND(o.est_minutes, 1) AS est_minutes,
    o.error_code
FROM v$asm_operation o
LEFT JOIN v$asm_diskgroup dg
    ON dg.group_number = o.group_number
ORDER BY
    dg.name,
    o.operation;
