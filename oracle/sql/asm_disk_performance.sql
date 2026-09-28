/*******************************************************************************
*
* Script Name: asm_disk_performance.sql
* Title: ASM Disk Performance
* Tags: ASM, Performance, Storage, IO
* Purpose: Display ASM disk I/O operations, throughput, and average response times
*
* Description:
*   Provides a detailed performance breakdown for Oracle Automatic Storage
*   Management (ASM) disks. It reports read and write I/O counts, megabytes
*   transferred, total I/O time, average read and write response latency
*   in milliseconds, and cumulative I/O error counts. Accepts an optional
*   diskgroup name filter.
*
* Parameters:
*   &1 - (Optional) Diskgroup name to filter (e.g. DATA). Default is all diskgroups.
*
* Required Privileges:
*   - SELECT on V$ASM_DISK_STAT (or V$ASM_DISK)
*   - SELECT on V$ASM_DISKGROUP
*
* Output Format:
*   - Disk Group name
*   - Failgroup and Disk Number
*   - Disk Name and OS Path
*   - Total Reads and Writes
*   - Read MB and Write MB
*   - Average Read Latency (ms) and Average Write Latency (ms)
*   - Read and Write I/O Error Counts
*
* Example Usage:
*   sqlplus / as sysasm @asm_disk_performance.sql
*   sqlplus / as sysasm @asm_disk_performance.sql DATA
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

COLUMN diskgroup_name FORMAT A20           HEADING 'Disk Group'
COLUMN failgroup      FORMAT A18 TRUNC     HEADING 'Fail Group'
COLUMN disk_number    FORMAT 9990          HEADING 'Disk#'
COLUMN disk_name      FORMAT A22 TRUNC     HEADING 'Disk Name'
COLUMN reads          FORMAT 999,999,990   HEADING 'Reads'
COLUMN writes         FORMAT 999,999,990   HEADING 'Writes'
COLUMN read_mb        FORMAT 999,999,990.0 HEADING 'Read MB'
COLUMN write_mb       FORMAT 999,999,990.0 HEADING 'Write MB'
COLUMN avg_read_ms    FORMAT 999,990.00    HEADING 'Avg Rd ms'
COLUMN avg_write_ms   FORMAT 999,990.00    HEADING 'Avg Wr ms'
COLUMN read_errs      FORMAT 999,990       HEADING 'Rd Errs'
COLUMN write_errs     FORMAT 999,990       HEADING 'Wr Errs'
COLUMN path           FORMAT A36 TRUNC     HEADING 'OS Path'

BREAK ON diskgroup_name SKIP 1 ON REPORT
COMPUTE SUM OF reads writes read_mb write_mb read_errs write_errs ON diskgroup_name
COMPUTE SUM OF reads writes read_mb write_mb read_errs write_errs ON REPORT

PROMPT
PROMPT === ASM Disk Performance ===
PROMPT

SELECT
    NVL(dg.name, 'HEADER_ONLY') AS diskgroup_name,
    d.failgroup,
    d.disk_number,
    d.name AS disk_name,
    d.reads,
    d.writes,
    ROUND(d.bytes_read / 1024 / 1024, 1) AS read_mb,
    ROUND(d.bytes_written / 1024 / 1024, 1) AS write_mb,
    ROUND(d.read_time * 1000 / NULLIF(d.reads, 0), 2) AS avg_read_ms,
    ROUND(d.write_time * 1000 / NULLIF(d.writes, 0), 2) AS avg_write_ms,
    d.read_errs,
    d.write_errs,
    d.path
FROM v$asm_disk_stat d
LEFT JOIN v$asm_diskgroup dg
    ON dg.group_number = d.group_number
WHERE dg.name = NVL(:dg_filter, dg.name)
   OR (:dg_filter IS NULL AND d.group_number = 0)
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
COLUMN reads CLEAR
COLUMN writes CLEAR
COLUMN read_mb CLEAR
COLUMN write_mb CLEAR
COLUMN avg_read_ms CLEAR
COLUMN avg_write_ms CLEAR
COLUMN read_errs CLEAR
COLUMN write_errs CLEAR
COLUMN path CLEAR
COLUMN c_dg CLEAR

SET FEEDBACK ON
SET VERIFY ON
