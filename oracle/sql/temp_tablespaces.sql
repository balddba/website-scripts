/*******************************************************************************
*
* Script Name: temp_tablespaces.sql
* Title: Temporary tablespaces
* Tags: Tablespaces, Temp, Sessions
* Purpose: Report temporary tablespaces, tempfiles, sort segments, and current temp consumers
*
* Description:
*   Lists every tablespace with CONTENTS='TEMPORARY', its tempfiles from
*   DBA_TEMP_FILES and V$TEMPFILE, RAC sort-segment allocation from
*   GV$SORT_SEGMENT (with SID and serial of current users), and sessions
*   currently holding temp from GV$TEMPSEG_USAGE (V$SORT_USAGE). Used space
*   is sort-segment used blocks, not file size. Covers every RAC instance.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on DBA_TABLESPACES
*   - SELECT on DBA_TEMP_FILES
*   - SELECT on V$TEMPFILE
*   - SELECT on GV$SORT_SEGMENT
*   - SELECT on GV$TEMPSEG_USAGE
*   - SELECT on GV$SESSION
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Temporary tablespace status, extent management, and allocated size
*   - Tempfile location, status, size, autoextend, and max size
*   - Sort-segment used and free space per instance, with SID and serial
*   - Current temp users: username, SID, SQL ID, tablespace, segtype, and MB
*
* Example Usage:
*   SQL> @temp_tablespaces.sql
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

COLUMN tablespace_name FORMAT A24            HEADING 'Tablespace'
COLUMN status          FORMAT A9             HEADING 'Status'
COLUMN extent_mgt      FORMAT A10            HEADING 'Extent Mgt'
COLUMN allocation      FORMAT A10            HEADING 'Allocation'
COLUMN bigfile         FORMAT A7             HEADING 'Bigfile'
COLUMN block_size      FORMAT 99999          HEADING 'Blk Sz'
COLUMN files           FORMAT 9990           HEADING 'Files'
COLUMN size_mb         FORMAT 999,999,990.0  HEADING 'Size MB'
COLUMN max_mb          FORMAT 999,999,990.0  HEADING 'Max MB'
COLUMN used_mb         FORMAT 999,999,990.0  HEADING 'Used MB'
COLUMN free_mb         FORMAT 999,999,990.0  HEADING 'Free MB'
COLUMN pct_used        FORMAT 990.0          HEADING 'Pct Used'
COLUMN file_id         FORMAT 9999           HEADING 'File#'
COLUMN file_name       FORMAT A70            HEADING 'File Name'
COLUMN file_status     FORMAT A9             HEADING 'Status'
COLUMN enabled         FORMAT A12            HEADING 'Enabled'
COLUMN autoextensible  FORMAT A10            HEADING 'Autoextend'
COLUMN inst_id         FORMAT 999            HEADING 'Inst'
COLUMN current_users   FORMAT 999,990        HEADING 'Users'
COLUMN total_mb        FORMAT 999,999,990.0  HEADING 'Total MB'
COLUMN added_extents   FORMAT 999,999,990    HEADING 'Added Ext'
COLUMN max_used_mb     FORMAT 999,999,990.0  HEADING 'Max Used MB'
COLUMN username        FORMAT A26            HEADING 'Username'
COLUMN sid             FORMAT 99999          HEADING 'SID'
COLUMN serial#         FORMAT 99999999       HEADING 'Serial#'
COLUMN sql_id          FORMAT A13            HEADING 'SQL ID'
COLUMN segtype         FORMAT A12            HEADING 'Seg Type'
COLUMN extents         FORMAT 999,990        HEADING 'Extents'
COLUMN blocks          FORMAT 999,999,990    HEADING 'Blocks'

PROMPT
PROMPT === Temporary tablespaces ===
PROMPT

SELECT
    ts.tablespace_name,
    ts.status,
    ts.extent_management AS extent_mgt,
    ts.allocation_type AS allocation,
    ts.bigfile,
    ts.block_size,
    NVL(tf.files, 0) AS files,
    ROUND(NVL(tf.bytes, 0) / 1024 / 1024, 1) AS size_mb,
    ROUND(NVL(tf.maxbytes, 0) / 1024 / 1024, 1) AS max_mb,
    ROUND(NVL(ss.used_bytes, 0) / 1024 / 1024, 1) AS used_mb,
    ROUND(
        (NVL(tf.bytes, 0) - NVL(ss.used_bytes, 0)) / 1024 / 1024,
        1
    ) AS free_mb,
    ROUND(
        NVL(ss.used_bytes, 0) / NULLIF(tf.bytes, 0) * 100,
        1
    ) AS pct_used
FROM dba_tablespaces ts
LEFT JOIN (
    SELECT
        tablespace_name,
        COUNT(*) AS files,
        SUM(bytes) AS bytes,
        SUM(CASE WHEN autoextensible = 'YES' THEN maxbytes ELSE bytes END) AS maxbytes
    FROM dba_temp_files
    GROUP BY tablespace_name
) tf ON tf.tablespace_name = ts.tablespace_name
LEFT JOIN (
    SELECT
        ss.tablespace_name,
        SUM(ss.used_blocks * ts_blk.block_size) AS used_bytes
    FROM gv$sort_segment ss
    JOIN dba_tablespaces ts_blk
      ON ts_blk.tablespace_name = ss.tablespace_name
    GROUP BY ss.tablespace_name
) ss ON ss.tablespace_name = ts.tablespace_name
WHERE ts.contents = 'TEMPORARY'
ORDER BY ts.tablespace_name;

PROMPT
PROMPT === Tempfiles ===
PROMPT

SELECT
    tf.tablespace_name,
    tf.file_id,
    tf.file_name,
    NVL(vt.status, tf.status) AS file_status,
    vt.enabled,
    tf.autoextensible,
    ROUND(tf.bytes / 1024 / 1024, 1) AS size_mb,
    CASE
        WHEN tf.autoextensible = 'YES'
        THEN ROUND(tf.maxbytes / 1024 / 1024, 1)
    END AS max_mb
FROM dba_temp_files tf
LEFT JOIN v$tempfile vt
  ON vt.file# = tf.file_id
ORDER BY
    tf.tablespace_name,
    tf.file_id;

PROMPT
PROMPT === Sort segments (GV$SORT_SEGMENT) ===
PROMPT

SELECT
    ss.inst_id,
    s.sid,
    s.serial#,
    ss.tablespace_name,
    ss.current_users,
    ROUND(ss.total_blocks * ts.block_size / 1024 / 1024, 1) AS total_mb,
    ROUND(ss.used_blocks * ts.block_size / 1024 / 1024, 1) AS used_mb,
    ROUND(ss.free_blocks * ts.block_size / 1024 / 1024, 1) AS free_mb,
    ss.added_extents,
    ROUND(ss.max_used_blocks * ts.block_size / 1024 / 1024, 1) AS max_used_mb
FROM gv$sort_segment ss
JOIN dba_tablespaces ts
  ON ts.tablespace_name = ss.tablespace_name
LEFT JOIN gv$tempseg_usage u
  ON u.inst_id = ss.inst_id
 AND u.tablespace = ss.tablespace_name
LEFT JOIN gv$session s
  ON s.inst_id = u.inst_id
 AND s.saddr = u.session_addr
ORDER BY
    ss.tablespace_name,
    ss.inst_id,
    s.sid;

PROMPT
PROMPT === Current temp segment usage (GV$TEMPSEG_USAGE) ===
PROMPT

SELECT
    u.inst_id,
    u.username,
    s.sid,
    s.serial#,
    u.sql_id,
    u.tablespace AS tablespace_name,
    u.segtype,
    u.extents,
    u.blocks,
    ROUND(u.blocks * ts.block_size / 1024 / 1024, 1) AS used_mb
FROM gv$tempseg_usage u
LEFT JOIN gv$session s
  ON s.inst_id = u.inst_id
 AND s.saddr = u.session_addr
LEFT JOIN dba_tablespaces ts
  ON ts.tablespace_name = u.tablespace
ORDER BY
    u.blocks DESC,
    u.inst_id,
    u.username;

COLUMN tablespace_name CLEAR
COLUMN status CLEAR
COLUMN extent_mgt CLEAR
COLUMN allocation CLEAR
COLUMN bigfile CLEAR
COLUMN block_size CLEAR
COLUMN files CLEAR
COLUMN size_mb CLEAR
COLUMN max_mb CLEAR
COLUMN used_mb CLEAR
COLUMN free_mb CLEAR
COLUMN pct_used CLEAR
COLUMN file_id CLEAR
COLUMN file_name CLEAR
COLUMN file_status CLEAR
COLUMN enabled CLEAR
COLUMN autoextensible CLEAR
COLUMN inst_id CLEAR
COLUMN current_users CLEAR
COLUMN total_mb CLEAR
COLUMN added_extents CLEAR
COLUMN max_used_mb CLEAR
COLUMN username CLEAR
COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN sql_id CLEAR
COLUMN segtype CLEAR
COLUMN extents CLEAR
COLUMN blocks CLEAR

SET FEEDBACK ON
SET VERIFY ON
