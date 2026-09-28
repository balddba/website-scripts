/*******************************************************************************
*
* Script Name: asm_disk_group_summary.sql
* Title: ASM Disk Group Summary
* Tags: ASM, Storage, Capacity, Summary
* Purpose: Display a concise summary of all ASM disk groups with status, disk count, capacity, and compatibility
*
* Description:
*   Generates a high-level, compact summary of all Automatic Storage Management
*   (ASM) disk groups. It presents group number, state, redundancy type,
*   active disk count, offline disk count, raw total and free storage in GB,
*   usable file storage in GB, percentage used, and software compatibility
*   levels. Accepts an optional diskgroup name filter.
*
* Parameters:
*   &1 - (Optional) Diskgroup name to filter (e.g. DATA). Default is all diskgroups (%).
*
* Required Privileges:
*   - SELECT on V$ASM_DISKGROUP
*   - SELECT on V$ASM_DISK
*
* Output Format:
*   - Group Number
*   - Disk Group Name
*   - State (MOUNTED, DISMOUNTED, etc.)
*   - Redundancy Type (EXTERN, NORMAL, HIGH, FLEX)
*   - Total Member Disk Count
*   - Offline Disk Count
*   - Total Capacity in GB
*   - Free Capacity in GB
*   - Usable File Capacity in GB
*   - Capacity Used Percentage
*   - ASM Compatibility and RDBMS Compatibility
*
* Example Usage:
*   sqlplus / as sysasm @asm_disk_group_summary.sql
*   sqlplus / as sysasm @asm_disk_group_summary.sql DATA
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET LINESIZE 240
SET PAGESIZE 100
SET VERIFY OFF
SET FEEDBACK OFF
SET TRIMSPOOL ON
SET TAB OFF

COLUMN c_dg NEW_VALUE p_dg NOPRINT
SELECT NVL(CAST(UPPER(TRIM('&1')) AS VARCHAR2(128)), '%') AS c_dg FROM dual;

VARIABLE dg_filter VARCHAR2(128)

BEGIN
    IF '&&p_dg' = '%' THEN
        :dg_filter := NULL;
    ELSE
        :dg_filter := '&&p_dg';
    END IF;
END;
/

COLUMN group_number    FORMAT 9990          HEADING 'Grp#'
COLUMN name            FORMAT A20           HEADING 'Disk Group'
COLUMN state           FORMAT A11           HEADING 'State'
COLUMN redundancy      FORMAT A10           HEADING 'Redundancy'
COLUMN disk_count      FORMAT 9990          HEADING 'Disks'
COLUMN offline_disks   FORMAT 9990          HEADING 'Offline'
COLUMN total_gb        FORMAT 999,990.0     HEADING 'Total GB'
COLUMN free_gb         FORMAT 999,990.0     HEADING 'Free GB'
COLUMN usable_file_gb  FORMAT 999,990.0     HEADING 'Usable GB'
COLUMN pct_used        FORMAT 990.0         HEADING '% Used'
COLUMN compatibility   FORMAT A12           HEADING 'ASM Compat'
COLUMN db_compat       FORMAT A12           HEADING 'RDBMS Compat'

BREAK ON REPORT
COMPUTE SUM OF total_gb free_gb usable_file_gb ON REPORT

PROMPT
PROMPT === ASM Disk Group Summary ===
PROMPT

SELECT
    dg.group_number,
    dg.name,
    dg.state,
    dg.type AS redundancy,
    NVL(d.disk_count, 0) AS disk_count,
    dg.offline_disks,
    ROUND(dg.total_mb / 1024, 1) AS total_gb,
    ROUND(dg.free_mb / 1024, 1) AS free_gb,
    ROUND(dg.usable_file_mb / 1024, 1) AS usable_file_gb,
    ROUND((dg.total_mb - dg.free_mb) / NULLIF(dg.total_mb, 0) * 100, 1) AS pct_used,
    dg.compatibility,
    dg.database_compatibility AS db_compat
FROM v$asm_diskgroup dg
LEFT JOIN (
    SELECT
        group_number,
        COUNT(*) AS disk_count
    FROM v$asm_disk
    GROUP BY group_number
) d
    ON d.group_number = dg.group_number
WHERE dg.name = NVL(:dg_filter, dg.name)
ORDER BY dg.name;

CLEAR COMPUTES
CLEAR BREAKS

COLUMN group_number CLEAR
COLUMN name CLEAR
COLUMN state CLEAR
COLUMN redundancy CLEAR
COLUMN disk_count CLEAR
COLUMN offline_disks CLEAR
COLUMN total_gb CLEAR
COLUMN free_gb CLEAR
COLUMN usable_file_gb CLEAR
COLUMN pct_used CLEAR
COLUMN compatibility CLEAR
COLUMN db_compat CLEAR
COLUMN c_dg CLEAR

SET FEEDBACK ON
SET VERIFY ON
