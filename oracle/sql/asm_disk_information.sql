/*******************************************************************************
*
* Script Name: asm_disk_information.sql
* Title: ASM Disk Information
* Tags: ASM, Storage, Disks
* Purpose: Display comprehensive inventory, state, capacity, and path details for ASM member and candidate disks
*
* Description:
*   Provides a detailed inventory of Automatic Storage Management (ASM) disks.
*   Reports disk group membership, disk number, disk name, failure group,
*   mount status, header status, mode status, state, voting file status,
*   sector size, OS path, total/free capacity in GB, and percentage used.
*   Accepts optional diskgroup and disk name filters.
*
* Parameters:
*   &1 - (Optional) Diskgroup name to filter (e.g. DATA). Default is all diskgroups (%).
*   &2 - (Optional) Disk name to filter (e.g. DATA_0000). Default is all disks (%).
*
* Required Privileges:
*   - SELECT on V$ASM_DISK
*   - SELECT on V$ASM_DISKGROUP
*
* Output Format:
*   - Disk Group name
*   - Failgroup and Failgroup Type
*   - Disk Number and Disk Name
*   - Mount, Header, Mode, and Disk State
*   - Voting Disk Flag (VOTING_FILE)
*   - Total GB, Free GB, and Percent Used
*   - Logical Sector Size
*   - OS Device Path
*
* Example Usage:
*   sqlplus / as sysasm @asm_disk_information.sql
*   sqlplus / as sysasm @asm_disk_information.sql DATA
*   sqlplus / as sysasm @asm_disk_information.sql DATA DATA_0001
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
COLUMN c_disk NEW_VALUE p_disk NOPRINT
SELECT
    NVL(CAST(UPPER(TRIM('&1')) AS VARCHAR2(128)), '%') AS c_dg,
    NVL(CAST(UPPER(TRIM('&2')) AS VARCHAR2(128)), '%') AS c_disk
FROM dual;

VARIABLE dg_filter VARCHAR2(128)
VARIABLE disk_filter VARCHAR2(128)

BEGIN
    IF '&&p_dg' = '%' THEN
        :dg_filter := NULL;
    ELSE
        :dg_filter := '&&p_dg';
    END IF;

    IF '&&p_disk' = '%' THEN
        :disk_filter := NULL;
    ELSE
        :disk_filter := '&&p_disk';
    END IF;
END;
/

COLUMN diskgroup_name FORMAT A18           HEADING 'Disk Group'
COLUMN failgroup      FORMAT A16 TRUNC     HEADING 'Fail Group'
COLUMN disk_number    FORMAT 9990          HEADING 'Disk#'
COLUMN disk_name      FORMAT A20 TRUNC     HEADING 'Disk Name'
COLUMN mount_status   FORMAT A8            HEADING 'Mount'
COLUMN header_status  FORMAT A11           HEADING 'Header'
COLUMN mode_status    FORMAT A7            HEADING 'Mode'
COLUMN disk_state     FORMAT A8            HEADING 'State'
COLUMN voting_file    FORMAT A6            HEADING 'Voting'
COLUMN total_gb       FORMAT 999,990.0     HEADING 'Total GB'
COLUMN free_gb        FORMAT 999,990.0     HEADING 'Free GB'
COLUMN pct_used       FORMAT 990.0         HEADING '% Used'
COLUMN sector_size    FORMAT 99990         HEADING 'Sector'
COLUMN path           FORMAT A40 TRUNC     HEADING 'OS Device Path'

BREAK ON diskgroup_name SKIP 1 ON REPORT
COMPUTE SUM OF total_gb free_gb ON diskgroup_name
COMPUTE SUM OF total_gb free_gb ON REPORT

PROMPT
PROMPT === ASM Disk Information ===
PROMPT

SELECT
    NVL(dg.name, 'CANDIDATE/DISMOUNTED') AS diskgroup_name,
    d.failgroup,
    d.disk_number,
    d.name AS disk_name,
    d.mount_status,
    d.header_status,
    d.mode_status,
    d.state AS disk_state,
    d.voting_file,
    ROUND(d.total_mb / 1024, 1) AS total_gb,
    ROUND(d.free_mb / 1024, 1) AS free_gb,
    ROUND((d.total_mb - d.free_mb) / NULLIF(d.total_mb, 0) * 100, 1) AS pct_used,
    d.sector_size,
    d.path
FROM v$asm_disk d
LEFT JOIN v$asm_diskgroup dg
    ON dg.group_number = d.group_number
WHERE (dg.name = NVL(:dg_filter, dg.name) OR (:dg_filter IS NULL AND d.group_number = 0))
  AND (d.name = NVL(:disk_filter, d.name) OR :disk_filter IS NULL)
ORDER BY
    dg.name,
    d.failgroup,
    d.disk_number;

CLEAR COMPUTES
CLEAR BREAKS

COLUMN diskgroup_name CLEAR
COLUMN failgroup CLEAR
COLUMN disk_number CLEAR
COLUMN disk_name CLEAR
COLUMN mount_status CLEAR
COLUMN header_status CLEAR
COLUMN mode_status CLEAR
COLUMN disk_state CLEAR
COLUMN voting_file CLEAR
COLUMN total_gb CLEAR
COLUMN free_gb CLEAR
COLUMN pct_used CLEAR
COLUMN sector_size CLEAR
COLUMN path CLEAR
COLUMN c_dg CLEAR
COLUMN c_disk CLEAR

SET FEEDBACK ON
SET VERIFY ON
