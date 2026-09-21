/*******************************************************************************
*
* Script Name: autoextend_report.sql
* Title: Datafile autoextend
* Tags: Capacity, Datafiles
* Purpose: Report autoextend settings for datafiles and tempfiles including next and max size
*
* Description:
*   Lists every datafile and tempfile with current size, autoextend flag,
*   next increment, and maximum size. Increment is converted from Oracle
*   blocks using the tablespace block size. Tempfiles are included because
*   they autoextend independently of permanent datafiles.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on DBA_DATA_FILES
*   - SELECT on DBA_TEMP_FILES
*   - SELECT on DBA_TABLESPACES
*
* Output Format:
*   - Tablespace type, name, file id, and file name
*   - File status and autoextend flag
*   - Current size, next increment, and max size in MB
*
* Example Usage:
*   SQL> @autoextend_report.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET LINESIZE 220
SET PAGESIZE 100

COLUMN ts_type         FORMAT A10            HEADING 'TS Type'
COLUMN tablespace_name FORMAT A25            HEADING 'Tablespace'
COLUMN file_id         FORMAT 9999           HEADING 'File#'
COLUMN file_name       FORMAT A70            HEADING 'File Name'
COLUMN status          FORMAT A9             HEADING 'Status'
COLUMN autoextensible  FORMAT A10            HEADING 'Autoextend'
COLUMN size_mb         FORMAT 999,999,990.0  HEADING 'Size MB'
COLUMN next_mb         FORMAT 999,999,990.0  HEADING 'Next MB'
COLUMN max_mb          FORMAT 999,999,990.0  HEADING 'Max MB'

SELECT
    ts.contents AS ts_type,
    df.tablespace_name,
    df.file_id,
    df.file_name,
    df.status,
    df.autoextensible,
    ROUND(df.bytes / 1024 / 1024, 1) AS size_mb,
    CASE
        WHEN df.autoextensible = 'YES'
        THEN ROUND(df.increment_by * ts.block_size / 1024 / 1024, 1)
    END AS next_mb,
    CASE
        WHEN df.autoextensible = 'YES'
        THEN ROUND(df.maxbytes / 1024 / 1024, 1)
    END AS max_mb
FROM dba_data_files df
JOIN dba_tablespaces ts ON ts.tablespace_name = df.tablespace_name
UNION ALL
SELECT
    ts.contents AS ts_type,
    tf.tablespace_name,
    tf.file_id,
    tf.file_name,
    tf.status,
    tf.autoextensible,
    ROUND(tf.bytes / 1024 / 1024, 1) AS size_mb,
    CASE
        WHEN tf.autoextensible = 'YES'
        THEN ROUND(tf.increment_by * ts.block_size / 1024 / 1024, 1)
    END AS next_mb,
    CASE
        WHEN tf.autoextensible = 'YES'
        THEN ROUND(tf.maxbytes / 1024 / 1024, 1)
    END AS max_mb
FROM dba_temp_files tf
JOIN dba_tablespaces ts ON ts.tablespace_name = tf.tablespace_name
ORDER BY tablespace_name, file_id;
