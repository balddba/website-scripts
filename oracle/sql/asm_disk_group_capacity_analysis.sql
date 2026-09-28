/*******************************************************************************
*
* Script Name: asm_disk_group_capacity_analysis.sql
* Title: ASM Disk Group Information and Capacity Analysis
* Tags: ASM, Storage, Capacity, Forecasting, Diskgroup
* Purpose: Provide in-depth capacity planning and redundancy loss safety analysis for ASM disk groups
*
* Description:
*   Performs comprehensive capacity and failure-tolerance analysis for Oracle
*   Automatic Storage Management (ASM) disk groups. It evaluates raw space,
*   mirror overhead, required mirror free space (space required to safely
*   rebalance after disk loss), usable file space under failure scenarios,
*   and member disk utilization variance/skew. Accepts an optional diskgroup
*   name filter.
*
* Parameters:
*   &1 - (Optional) Diskgroup name to filter (e.g. DATA). Default is all diskgroups (%).
*
* Required Privileges:
*   - SELECT on V$ASM_DISKGROUP
*   - SELECT on V$ASM_DISK
*
* Output Format:
*   - Disk Group Capacity & Safety Analysis:
*     * Disk Group name, state, redundancy type
*     * Raw Total GB, Raw Free GB, Raw Used %
*     * Required Mirror Free GB (reserved for disk loss rebalance)
*     * Usable File GB (net file capacity available with redundancy)
*     * Offline Disks count
*   - Member Disk Distribution and Skew Analysis:
*     * Disk Group name, disk count
*     * Min Disk Used %, Max Disk Used %, Avg Disk Used %
*     * Disk Imbalance / Skew %
*
* Example Usage:
*   sqlplus / as sysasm @asm_disk_group_capacity_analysis.sql
*   sqlplus / as sysasm @asm_disk_group_capacity_analysis.sql DATA
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

COLUMN name                   FORMAT A18           HEADING 'Disk Group'
COLUMN state                  FORMAT A11           HEADING 'State'
COLUMN redundancy             FORMAT A10           HEADING 'Redundancy'
COLUMN total_gb               FORMAT 999,990.0     HEADING 'Raw Total GB'
COLUMN free_gb                FORMAT 999,990.0     HEADING 'Raw Free GB'
COLUMN raw_pct_used           FORMAT 990.0         HEADING 'Raw % Used'
COLUMN req_mirror_gb          FORMAT 999,990.0     HEADING 'Req Mirror GB'
COLUMN usable_file_gb         FORMAT 999,990.0     HEADING 'Usable File GB'
COLUMN safe_free_pct          FORMAT 990.0         HEADING 'Safe Free %'
COLUMN offline_disks          FORMAT 9990          HEADING 'Offline'

COLUMN skew_dg_name           FORMAT A18           HEADING 'Disk Group'
COLUMN disk_count             FORMAT 9990          HEADING 'Disks'
COLUMN min_disk_used_pct      FORMAT 990.0         HEADING 'Min Disk %'
COLUMN max_disk_used_pct      FORMAT 990.0         HEADING 'Max Disk %'
COLUMN avg_disk_used_pct      FORMAT 990.0         HEADING 'Avg Disk %'
COLUMN skew_pct               FORMAT 990.0         HEADING 'Skew/Diff %'

BREAK ON REPORT
COMPUTE SUM OF total_gb free_gb req_mirror_gb usable_file_gb ON REPORT

PROMPT
PROMPT === ASM Disk Group Capacity & Safety Analysis ===
PROMPT

SELECT
    name,
    state,
    type AS redundancy,
    ROUND(total_mb / 1024, 1) AS total_gb,
    ROUND(free_mb / 1024, 1) AS free_gb,
    ROUND((total_mb - free_mb) / NULLIF(total_mb, 0) * 100, 1) AS raw_pct_used,
    ROUND(required_mirror_free_mb / 1024, 1) AS req_mirror_gb,
    ROUND(usable_file_mb / 1024, 1) AS usable_file_gb,
    ROUND(usable_file_mb / NULLIF(total_mb / CASE type WHEN 'NORMAL' THEN 2 WHEN 'HIGH' THEN 3 ELSE 1 END, 0) * 100, 1) AS safe_free_pct,
    offline_disks
FROM v$asm_diskgroup
WHERE name = NVL(:dg_filter, name)
ORDER BY name;

CLEAR COMPUTES
CLEAR BREAKS

PROMPT
PROMPT === Member Disk Distribution and Skew Analysis ===
PROMPT

SELECT
    dg.name AS skew_dg_name,
    COUNT(d.disk_number) AS disk_count,
    ROUND(MIN((d.total_mb - d.free_mb) / NULLIF(d.total_mb, 0) * 100), 1) AS min_disk_used_pct,
    ROUND(MAX((d.total_mb - d.free_mb) / NULLIF(d.total_mb, 0) * 100), 1) AS max_disk_used_pct,
    ROUND(AVG((d.total_mb - d.free_mb) / NULLIF(d.total_mb, 0) * 100), 1) AS avg_disk_used_pct,
    ROUND(MAX((d.total_mb - d.free_mb) / NULLIF(d.total_mb, 0) * 100) - MIN((d.total_mb - d.free_mb) / NULLIF(d.total_mb, 0) * 100), 1) AS skew_pct
FROM v$asm_disk d
JOIN v$asm_diskgroup dg
    ON dg.group_number = d.group_number
WHERE dg.name = NVL(:dg_filter, dg.name)
GROUP BY dg.name
ORDER BY dg.name;

COLUMN name CLEAR
COLUMN state CLEAR
COLUMN redundancy CLEAR
COLUMN total_gb CLEAR
COLUMN free_gb CLEAR
COLUMN raw_pct_used CLEAR
COLUMN req_mirror_gb CLEAR
COLUMN usable_file_gb CLEAR
COLUMN safe_free_pct CLEAR
COLUMN offline_disks CLEAR
COLUMN skew_dg_name CLEAR
COLUMN disk_count CLEAR
COLUMN min_disk_used_pct CLEAR
COLUMN max_disk_used_pct CLEAR
COLUMN avg_disk_used_pct CLEAR
COLUMN skew_pct CLEAR
COLUMN c_dg CLEAR

SET FEEDBACK ON
SET VERIFY ON
