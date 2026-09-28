/*******************************************************************************
*
* Script Name: asm_disk_group_information.sql
* Title: ASM Disk Group Information
* Tags: ASM, Storage, Diskgroup, Configuration
* Purpose: Report configuration, redundancy, allocation unit size, sector size, compatibility, and attributes for ASM disk groups
*
* Description:
*   Reports detailed configuration settings for Oracle Automatic Storage
*   Management (ASM) disk groups. It details disk group state, redundancy
*   type (EXTERN, NORMAL, HIGH, FLEX), allocation unit (AU) size, logical
*   and physical sector sizes, disk counts, offline disk counts, compatibility
*   settings (ASM, RDBMS), and all customized diskgroup attributes. Accepts
*   an optional diskgroup name filter.
*
* Parameters:
*   &1 - (Optional) Diskgroup name to filter (e.g. DATA). Default is all diskgroups (%).
*
* Required Privileges:
*   - SELECT on V$ASM_DISKGROUP
*   - SELECT on V$ASM_ATTRIBUTE
*
* Output Format:
*   - Disk Group Configuration: Name, state, redundancy, AU size (MB), sector sizes, disk counts, total/free GB, compatibility
*   - Disk Group Attributes: Group name, attribute name, attribute value, read-only flag
*
* Example Usage:
*   sqlplus / as sysasm @asm_disk_group_information.sql
*   sqlplus / as sysasm @asm_disk_group_information.sql DATA
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

COLUMN group_number           FORMAT 9990          HEADING 'Grp#'
COLUMN name                   FORMAT A20           HEADING 'Disk Group'
COLUMN state                  FORMAT A12           HEADING 'State'
COLUMN redundancy             FORMAT A10           HEADING 'Redundancy'
COLUMN allocation_unit_size_mb FORMAT 990.0        HEADING 'AU MB'
COLUMN sector_size            FORMAT 99990         HEADING 'Log Sec'
COLUMN logical_sector_size    FORMAT 99990         HEADING 'Phy Sec'
COLUMN total_gb               FORMAT 999,990.0     HEADING 'Total GB'
COLUMN free_gb                FORMAT 999,990.0     HEADING 'Free GB'
COLUMN offline_disks          FORMAT 9990          HEADING 'Offline'
COLUMN compatibility          FORMAT A14           HEADING 'ASM Compat'
COLUMN database_compatibility FORMAT A14           HEADING 'RDBMS Compat'

COLUMN attr_dg_name           FORMAT A20           HEADING 'Disk Group'
COLUMN attr_name              FORMAT A36           HEADING 'Attribute Name'
COLUMN attr_value             FORMAT A36 TRUNC     HEADING 'Attribute Value'
COLUMN read_only              FORMAT A6            HEADING 'RO'

PROMPT
PROMPT === ASM Disk Group Configuration ===
PROMPT

SELECT
    group_number,
    name,
    state,
    type AS redundancy,
    ROUND(allocation_unit_size / 1024 / 1024, 1) AS allocation_unit_size_mb,
    sector_size,
    logical_sector_size,
    ROUND(total_mb / 1024, 1) AS total_gb,
    ROUND(free_mb / 1024, 1) AS free_gb,
    offline_disks,
    compatibility,
    database_compatibility
FROM v$asm_diskgroup
WHERE name = NVL(:dg_filter, name)
ORDER BY name;

PROMPT
PROMPT === ASM Disk Group Attributes ===
PROMPT

SELECT
    dg.name AS attr_dg_name,
    a.name AS attr_name,
    a.value AS attr_value,
    a.read_only
FROM v$asm_attribute a
JOIN v$asm_diskgroup dg
    ON dg.group_number = a.group_number
WHERE dg.name = NVL(:dg_filter, dg.name)
ORDER BY
    dg.name,
    a.name;

COLUMN group_number CLEAR
COLUMN name CLEAR
COLUMN state CLEAR
COLUMN redundancy CLEAR
COLUMN allocation_unit_size_mb CLEAR
COLUMN sector_size CLEAR
COLUMN logical_sector_size CLEAR
COLUMN total_gb CLEAR
COLUMN free_gb CLEAR
COLUMN offline_disks CLEAR
COLUMN compatibility CLEAR
COLUMN database_compatibility CLEAR
COLUMN attr_dg_name CLEAR
COLUMN attr_name CLEAR
COLUMN attr_value CLEAR
COLUMN read_only CLEAR
COLUMN c_dg CLEAR

SET FEEDBACK ON
SET VERIFY ON
