/*******************************************************************************
*
* Script Name: tablespaces.sql
* Title: Tablespace inventory
* Tags: Capacity, Tablespaces, Encryption
* Purpose: Report every tablespace with type, size, usage, extent management, bigfile, compression, and encryption
*
* Description:
*   One row per tablespace in the current container. Permanent and undo usage
*   come from datafile size minus DBA_FREE_SPACE. Temporary usage is cached
*   temp extents across RAC instances. Encryption shows the algorithm from
*   V$ENCRYPTED_TABLESPACES when the tablespace is encrypted. Compression
*   shows the default COMPRESS FOR type when default table compression is
*   enabled. Sizes are allocated file bytes, not autoextend maximum.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on DBA_TABLESPACES
*   - SELECT on DBA_DATA_FILES
*   - SELECT on DBA_TEMP_FILES
*   - SELECT on DBA_FREE_SPACE
*   - SELECT on GV$TEMP_EXTENT_POOL
*   - SELECT on V$TABLESPACE
*   - SELECT on V$ENCRYPTED_TABLESPACES
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Status, tablespace name, contents type, and extent management
*   - Bigfile flag, default compression type, and encryption algorithm
*   - Allocated size, used space, and percent used in GB
*
* Example Usage:
*   SQL> @tablespaces.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET LINESIZE 200
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN status          FORMAT A9             HEADING 'Status'
COLUMN tablespace_name FORMAT A24            HEADING 'Tablespace'
COLUMN ts_type         FORMAT A10            HEADING 'Type'
COLUMN extent_mgt      FORMAT A10            HEADING 'Extent Mgt'
COLUMN bigfile         FORMAT A7             HEADING 'Bigfile'
COLUMN compression     FORMAT A14            HEADING 'Compression'
COLUMN encryption      FORMAT A12            HEADING 'Encryption'
COLUMN size_gb         FORMAT 999,990.00     HEADING 'Size GB'
COLUMN used_gb         FORMAT 999,990.00     HEADING 'Used GB'
COLUMN pct_used        FORMAT 990.0          HEADING 'Pct Used'

BREAK ON REPORT
COMPUTE SUM OF size_gb used_gb ON REPORT

WITH ts_size AS (
    SELECT tablespace_name, SUM(bytes) AS bytes
    FROM dba_data_files
    GROUP BY tablespace_name
    UNION ALL
    SELECT tablespace_name, SUM(bytes) AS bytes
    FROM dba_temp_files
    GROUP BY tablespace_name
),
ts_used AS (
    SELECT
        df.tablespace_name,
        df.bytes - NVL(fs.bytes, 0) AS bytes
    FROM (
        SELECT tablespace_name, SUM(bytes) AS bytes
        FROM dba_data_files
        GROUP BY tablespace_name
    ) df
    LEFT JOIN (
        SELECT tablespace_name, SUM(bytes) AS bytes
        FROM dba_free_space
        GROUP BY tablespace_name
    ) fs ON fs.tablespace_name = df.tablespace_name
    UNION ALL
    SELECT tablespace_name, SUM(bytes_cached) AS bytes
    FROM gv$temp_extent_pool
    GROUP BY tablespace_name
)
SELECT
    ts.status,
    ts.tablespace_name,
    ts.contents AS ts_type,
    ts.extent_management AS extent_mgt,
    ts.bigfile,
    CASE
        WHEN ts.def_tab_compression = 'ENABLED'
        THEN NVL(ts.compress_for, 'ENABLED')
        ELSE 'DISABLED'
    END AS compression,
    CASE
        WHEN ts.encrypted = 'YES'
        THEN NVL(et.encryptionalg, 'YES')
        ELSE 'NO'
    END AS encryption,
    ROUND(NVL(sz.bytes, 0) / 1024 / 1024 / 1024, 2) AS size_gb,
    ROUND(NVL(us.bytes, 0) / 1024 / 1024 / 1024, 2) AS used_gb,
    ROUND(NVL(us.bytes, 0) / NULLIF(sz.bytes, 0) * 100, 1) AS pct_used
FROM dba_tablespaces ts
LEFT JOIN v$tablespace vt
    ON vt.name = ts.tablespace_name
LEFT JOIN v$encrypted_tablespaces et
    ON et.ts# = vt.ts#
LEFT JOIN ts_size sz
    ON sz.tablespace_name = ts.tablespace_name
LEFT JOIN ts_used us
    ON us.tablespace_name = ts.tablespace_name
ORDER BY ts.tablespace_name;
