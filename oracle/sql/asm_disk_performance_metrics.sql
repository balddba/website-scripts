/*******************************************************************************
*
* Script Name: asm_disk_performance_metrics.sql
* Title: ASM Disk Performance Metrics
* Tags: ASM, Performance, Metrics, IO, Storage
* Purpose: Display ASM disk I/O performance metrics and response times from V$ASM_DISK_IOSTAT
*
* Description:
*   Provides a detailed breakdown of I/O performance metrics for Automatic
*   Storage Management (ASM) disks using V$ASM_DISK_IOSTAT and V$ASM_DISKGROUP.
*   It displays read and write request counts, volume in megabytes, total I/O
*   time in seconds, average read and write latency in milliseconds, cold and
*   hot region I/O operations, and I/O error counts. Accepts an optional
*   diskgroup name filter.
*
* Parameters:
*   &1 - (Optional) Diskgroup name to filter (e.g. DATA). Default is all diskgroups (%).
*
* Required Privileges:
*   - SELECT on V$ASM_DISK_IOSTAT
*   - SELECT on V$ASM_DISKGROUP
*
* Output Format:
*   - Disk Group name
*   - Failgroup and Disk Number
*   - Disk Name
*   - Total Reads and Writes
*   - Read MB and Write MB
*   - Read Time (s) and Write Time (s)
*   - Average Read Latency (ms) and Average Write Latency (ms)
*   - Hot/Cold Reads and Writes
*   - Read and Write Error Counts
*
* Example Usage:
*   sqlplus / as sysasm @asm_disk_performance_metrics.sql
*   sqlplus / as sysasm @asm_disk_performance_metrics.sql DATA
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

COLUMN diskgroup_name FORMAT A18           HEADING 'Disk Group'
COLUMN failgroup      FORMAT A16 TRUNC     HEADING 'Fail Group'
COLUMN disk_number    FORMAT 9990          HEADING 'Disk#'
COLUMN disk_name      FORMAT A20 TRUNC     HEADING 'Disk Name'
COLUMN reads          FORMAT 999,999,990   HEADING 'Reads'
COLUMN writes         FORMAT 999,999,990   HEADING 'Writes'
COLUMN read_mb        FORMAT 999,999,990.0 HEADING 'Read MB'
COLUMN write_mb       FORMAT 999,999,990.0 HEADING 'Write MB'
COLUMN read_time_s    FORMAT 999,990.00    HEADING 'Read Time(s)'
COLUMN write_time_s   FORMAT 999,990.00    HEADING 'Write Time(s)'
COLUMN avg_read_ms    FORMAT 999,990.00    HEADING 'Avg Rd ms'
COLUMN avg_write_ms   FORMAT 999,990.00    HEADING 'Avg Wr ms'
COLUMN cold_reads     FORMAT 999,999,990   HEADING 'Cold Rds'
COLUMN hot_reads      FORMAT 999,999,990   HEADING 'Hot Rds'
COLUMN read_errs      FORMAT 9990          HEADING 'Rd Errs'
COLUMN write_errs     FORMAT 9990          HEADING 'Wr Errs'

BREAK ON diskgroup_name SKIP 1 ON REPORT
COMPUTE SUM OF reads writes read_mb write_mb read_errs write_errs ON diskgroup_name
COMPUTE SUM OF reads writes read_mb write_mb read_errs write_errs ON REPORT

PROMPT
PROMPT === ASM Disk Performance Metrics (V$ASM_DISK_IOSTAT) ===
PROMPT

SELECT
    NVL(dg.name, 'UNKNOWN') AS diskgroup_name,
    d.failgroup,
    d.disk_number,
    d.disk_name,
    d.reads,
    d.writes,
    ROUND(d.bytes_read / 1024 / 1024, 1) AS read_mb,
    ROUND(d.bytes_written / 1024 / 1024, 1) AS write_mb,
    ROUND(d.read_time, 2) AS read_time_s,
    ROUND(d.write_time, 2) AS write_time_s,
    ROUND(d.read_time * 1000 / NULLIF(d.reads, 0), 2) AS avg_read_ms,
    ROUND(d.write_time * 1000 / NULLIF(d.writes, 0), 2) AS avg_write_ms,
    d.cold_reads,
    d.hot_reads,
    d.read_errs,
    d.write_errs
FROM (
    SELECT
        group_number,
        disk_number,
        failgroup,
        disk_name,
        reads,
        writes,
        bytes_read,
        bytes_written,
        read_time,
        write_time,
        cold_reads,
        hot_reads,
        read_errs,
        write_errs
    FROM (
        SELECT
            group_number,
            disk_number,
            failgroup,
            disk_name,
            reads,
            writes,
            bytes_read,
            bytes_written,
            read_time,
            write_time,
            cold_reads,
            hot_reads,
            read_errs,
            write_errs
        FROM (
            SELECT
                group_number,
                disk_number,
                failgroup,
                disk_name,
                reads,
                writes,
                bytes_read,
                bytes_written,
                read_time,
                write_time,
                cold_reads,
                hot_reads,
                read_errs,
                write_errs
            FROM (
                SELECT
                    io.group_number,
                    io.disk_number,
                    NVL(io.failgroup, 'N/A') AS failgroup,
                    NVL(io.disk_name, 'DISK_' || io.disk_number) AS disk_name,
                    io.reads,
                    io.writes,
                    io.bytes_read,
                    io.bytes_written,
                    io.read_time,
                    io.write_time,
                    io.cold_reads,
                    io.hot_reads,
                    io.read_errs,
                    io.write_errs
                FROM v$asm_disk_iostat io
            )
        )
    )
) d
LEFT JOIN v$asm_diskgroup dg
    ON dg.group_number = d.group_number
WHERE (dg.name = NVL(:dg_filter, dg.name) OR :dg_filter IS NULL)
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
COLUMN read_time_s CLEAR
COLUMN write_time_s CLEAR
COLUMN avg_read_ms CLEAR
COLUMN avg_write_ms CLEAR
COLUMN cold_reads CLEAR
COLUMN hot_reads CLEAR
COLUMN read_errs CLEAR
COLUMN write_errs CLEAR
COLUMN c_dg CLEAR

SET FEEDBACK ON
SET VERIFY ON
