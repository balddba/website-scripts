/*******************************************************************************
*
* Script Name: io_distribution.sql
* Title: I/O distribution
* Tags: IO, Performance, Storage
* Purpose: Report physical I/O by datafile, tempfile, tablespace, or device
*
* Description:
*   Combines V$FILESTAT with DBA_DATA_FILES and V$TEMPSTAT with DBA_TEMP_FILES.
*   Grouping is FILE (default), TABLESPACE, or DEVICE. Device is the ASM
*   diskgroup (+DATA) or the first filesystem path component (/u01). Times in
*   V$FILESTAT are hundredths of a second; average read and write time are
*   also shown in milliseconds. I/O by function comes from V$IOSTAT_FUNCTION
*   (11g+; the documented view behind older V$IOFUNCSTAT references). Press
*   Enter at the SQL*Plus prompt if no argument is passed.
*
* Parameters:
*   &1 - (Optional) Grouping: FILE | TABLESPACE | DEVICE. Default is FILE.
*
* Required Privileges:
*   - SELECT on V$FILESTAT
*   - SELECT on V$TEMPSTAT
*   - SELECT on DBA_DATA_FILES
*   - SELECT on DBA_TEMP_FILES
*   - SELECT on V$IOSTAT_FUNCTION
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Grouping key, file count, and file type when grouping by FILE
*   - Physical reads and writes, blocks read and written
*   - Read time, write time, and average I/O time
*   - Average read and write milliseconds, plus percent of total I/O
*   - I/O by function from V$IOSTAT_FUNCTION
*
* Example Usage:
*   SQL> @io_distribution.sql
*   SQL> @io_distribution.sql FILE
*   SQL> @io_distribution.sql TABLESPACE
*   SQL> @io_distribution.sql DEVICE
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 240
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

-- Optional &1: SQL*Plus prompts if omitted; Enter (empty) means FILE.
COLUMN c_group NEW_VALUE p_group NOPRINT
SELECT NVL(CAST(UPPER(TRIM('&1')) AS VARCHAR2(128)), 'FILE') AS c_group FROM dual;

VARIABLE grouping VARCHAR2(20)

BEGIN
    :grouping := '&&p_group';
    IF :grouping NOT IN ('FILE', 'TABLESPACE', 'DEVICE') THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Grouping must be FILE, TABLESPACE, or DEVICE (default FILE).'
        );
    END IF;
END;
/

COLUMN io_group      FORMAT A11               HEADING 'Grouping'
COLUMN io_target     FORMAT A70               HEADING 'Target'
COLUMN file_count    FORMAT 9990              HEADING 'Files'
COLUMN file_id       FORMAT 9999              HEADING 'File#'
COLUMN file_type     FORMAT A8                HEADING 'Type'
COLUMN tablespace_name FORMAT A24             HEADING 'Tablespace'
COLUMN phyrds        FORMAT 999,999,999,990   HEADING 'Phy Rds'
COLUMN phywrts       FORMAT 999,999,999,990   HEADING 'Phy Wrts'
COLUMN phyblkrd      FORMAT 999,999,999,990   HEADING 'Blk Rds'
COLUMN phyblkwrt     FORMAT 999,999,999,990   HEADING 'Blk Wrts'
COLUMN readtim       FORMAT 999,999,999,990   HEADING 'Read Tim'
COLUMN writetim      FORMAT 999,999,999,990   HEADING 'Write Tim'
COLUMN avgiotim      FORMAT 999,990.00        HEADING 'Avg IO'
COLUMN avg_read_ms   FORMAT 999,990.00        HEADING 'Avg Rd ms'
COLUMN avg_write_ms  FORMAT 999,990.00        HEADING 'Avg Wr ms'
COLUMN pct_reads     FORMAT 990.0             HEADING 'Pct Rd'
COLUMN pct_writes    FORMAT 990.0             HEADING 'Pct Wr'
COLUMN function_name FORMAT A36               HEADING 'Function'
COLUMN small_read_mb FORMAT 999,999,990.0     HEADING 'Sm Rd MB'
COLUMN small_write_mb FORMAT 999,999,990.0    HEADING 'Sm Wr MB'
COLUMN large_read_mb FORMAT 999,999,990.0     HEADING 'Lg Rd MB'
COLUMN large_write_mb FORMAT 999,999,990.0    HEADING 'Lg Wr MB'
COLUMN small_read_reqs FORMAT 999,999,999,990 HEADING 'Sm Rd Reqs'
COLUMN small_write_reqs FORMAT 999,999,999,990 HEADING 'Sm Wr Reqs'
COLUMN large_read_reqs FORMAT 999,999,999,990 HEADING 'Lg Rd Reqs'
COLUMN large_write_reqs FORMAT 999,999,999,990 HEADING 'Lg Wr Reqs'
COLUMN number_of_waits FORMAT 999,999,990     HEADING 'Waits'
COLUMN wait_time     FORMAT 999,999,999,990   HEADING 'Wait Time'

BREAK ON REPORT
COMPUTE SUM OF phyrds phywrts phyblkrd phyblkwrt readtim writetim ON REPORT

PROMPT
PROMPT === I/O distribution (&&p_group) ===
PROMPT
PROMPT Times are hundredths of a second. Avg Rd/Wr are milliseconds.
PROMPT

WITH file_io AS (
    SELECT
        'DATA' AS file_type,
        df.file_id,
        df.tablespace_name,
        df.file_name,
        CASE
            WHEN df.file_name LIKE '+%' THEN
                REGEXP_SUBSTR(df.file_name, '^\+[A-Za-z0-9_#$]+')
            WHEN REGEXP_LIKE(df.file_name, '^[A-Za-z]:\\') THEN
                REGEXP_SUBSTR(df.file_name, '^[A-Za-z]:\\[^\\]*')
            ELSE
                NVL(REGEXP_SUBSTR(df.file_name, '^/[^/]+'), df.file_name)
        END AS device_name,
        fs.phyrds,
        fs.phywrts,
        fs.phyblkrd,
        fs.phyblkwrt,
        fs.readtim,
        fs.writetim
    FROM v$filestat fs
    JOIN dba_data_files df
      ON df.file_id = fs.file#
    UNION ALL
    SELECT
        'TEMP' AS file_type,
        tf.file_id,
        tf.tablespace_name,
        tf.file_name,
        CASE
            WHEN tf.file_name LIKE '+%' THEN
                REGEXP_SUBSTR(tf.file_name, '^\+[A-Za-z0-9_#$]+')
            WHEN REGEXP_LIKE(tf.file_name, '^[A-Za-z]:\\') THEN
                REGEXP_SUBSTR(tf.file_name, '^[A-Za-z]:\\[^\\]*')
            ELSE
                NVL(REGEXP_SUBSTR(tf.file_name, '^/[^/]+'), tf.file_name)
        END AS device_name,
        ts.phyrds,
        ts.phywrts,
        ts.phyblkrd,
        ts.phyblkwrt,
        ts.readtim,
        ts.writetim
    FROM v$tempstat ts
    JOIN dba_temp_files tf
      ON tf.file_id = ts.file#
), grouped_io AS (
SELECT
    :grouping AS io_group,
    CASE :grouping
        WHEN 'TABLESPACE' THEN tablespace_name
        WHEN 'DEVICE' THEN device_name
        ELSE file_name
    END AS io_target,
    COUNT(*) AS file_count,
    CASE WHEN :grouping = 'FILE' THEN MAX(file_id) END AS file_id,
    CASE WHEN :grouping = 'FILE' THEN MAX(file_type) END AS file_type,
    CASE WHEN :grouping = 'FILE' THEN MAX(tablespace_name) END AS tablespace_name,
    SUM(phyrds) AS phyrds,
    SUM(phywrts) AS phywrts,
    SUM(phyblkrd) AS phyblkrd,
    SUM(phyblkwrt) AS phyblkwrt,
    SUM(readtim) AS readtim,
    SUM(writetim) AS writetim,
    ROUND(
        SUM(readtim + writetim) / NULLIF(SUM(phyrds + phywrts), 0),
        2
    ) AS avgiotim,
    ROUND(SUM(readtim) * 10 / NULLIF(SUM(phyrds), 0), 2) AS avg_read_ms,
    ROUND(SUM(writetim) * 10 / NULLIF(SUM(phywrts), 0), 2) AS avg_write_ms
FROM file_io
GROUP BY
    CASE :grouping
        WHEN 'TABLESPACE' THEN tablespace_name
        WHEN 'DEVICE' THEN device_name
        ELSE file_name
    END
)
SELECT
    grouped_io.*,
    ROUND(RATIO_TO_REPORT(phyrds) OVER () * 100, 1) AS pct_reads,
    ROUND(RATIO_TO_REPORT(phywrts) OVER () * 100, 1) AS pct_writes
FROM grouped_io
ORDER BY
    phyrds + phywrts DESC,
    io_target;

CLEAR COMPUTES
CLEAR BREAKS

PROMPT
PROMPT === I/O by function (V$IOSTAT_FUNCTION) ===
PROMPT

SELECT
    function_name,
    small_read_megabytes AS small_read_mb,
    small_write_megabytes AS small_write_mb,
    large_read_megabytes AS large_read_mb,
    large_write_megabytes AS large_write_mb,
    small_read_reqs,
    small_write_reqs,
    large_read_reqs,
    large_write_reqs,
    number_of_waits,
    wait_time
FROM v$iostat_function
ORDER BY
    small_read_reqs + small_write_reqs + large_read_reqs + large_write_reqs DESC,
    function_name;

COLUMN io_group CLEAR
COLUMN io_target CLEAR
COLUMN file_count CLEAR
COLUMN file_id CLEAR
COLUMN file_type CLEAR
COLUMN tablespace_name CLEAR
COLUMN phyrds CLEAR
COLUMN phywrts CLEAR
COLUMN phyblkrd CLEAR
COLUMN phyblkwrt CLEAR
COLUMN readtim CLEAR
COLUMN writetim CLEAR
COLUMN avgiotim CLEAR
COLUMN avg_read_ms CLEAR
COLUMN avg_write_ms CLEAR
COLUMN pct_reads CLEAR
COLUMN pct_writes CLEAR
COLUMN function_name CLEAR
COLUMN small_read_mb CLEAR
COLUMN small_write_mb CLEAR
COLUMN large_read_mb CLEAR
COLUMN large_write_mb CLEAR
COLUMN small_read_reqs CLEAR
COLUMN small_write_reqs CLEAR
COLUMN large_read_reqs CLEAR
COLUMN large_write_reqs CLEAR
COLUMN number_of_waits CLEAR
COLUMN wait_time CLEAR
COLUMN c_group CLEAR

SET FEEDBACK ON
SET VERIFY ON
