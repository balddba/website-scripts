/*******************************************************************************
*
* Script Name: lob_space_usage.sql
* Title: LOB Space Usage
* Tags: Storage, LOB, Space
* Purpose: Details BasicFiles and SecureFiles LOB segment sizes, tablespace, retention, compression, and deduplication settings from dba_lobs and dba_segments (optional &1 for schema/owner, defaults to '%').
*
* Description:
*   Reports LOB segments across the database or for a specified schema owner.
*   Compares LOB metadata from DBA_LOBS (storage type: BasicFiles vs SecureFiles,
*   in-row storage, retention, compression, deduplication, encryption) with
*   segment space allocated in DBA_SEGMENTS (including LOBSEGMENT and LOBINDEX
*   segments). Helps identify large LOBs and optimization opportunities such
*   as SecureFiles compression and deduplication.
*
* Parameters:
*   &1 - (Optional) Schema owner. Default is % (all schemas).
*
* Required Privileges:
*   - SELECT on DBA_LOBS
*   - SELECT on DBA_SEGMENTS
*
* Output Format:
*   - Owner, Table Name, and Column Name
*   - Tablespace Name
*   - SecureFiles flag and In-Row storage flag
*   - Compression, Deduplication, and Encryption settings
*   - LOB Segment Size (MB), Index Size (MB), and Total Size (MB)
*
* Example Usage:
*   sqlplus user/password@yourdb @lob_space_usage.sql
*   sqlplus user/password@yourdb @lob_space_usage.sql HR
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 200
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN c_owner NEW_VALUE p_owner NOPRINT
SELECT NVL(NULLIF(TRIM('&1'), ''), '%') AS c_owner FROM dual;

COLUMN owner           FORMAT A16            HEADING 'Owner'
COLUMN table_name      FORMAT A22            HEADING 'Table Name'
COLUMN column_name     FORMAT A20            HEADING 'Column Name'
COLUMN tablespace_name FORMAT A18            HEADING 'Tablespace'
COLUMN securefile      FORMAT A10            HEADING 'Securefile'
COLUMN in_row          FORMAT A6             HEADING 'In Row'
COLUMN compression     FORMAT A11            HEADING 'Compression'
COLUMN deduplication   FORMAT A13            HEADING 'Deduplication'
COLUMN encryption      FORMAT A10            HEADING 'Encryption'
COLUMN lob_mb          FORMAT 999,990.00     HEADING 'LOB MB'
COLUMN index_mb        FORMAT 999,990.00     HEADING 'Index MB'
COLUMN total_mb        FORMAT 999,990.00     HEADING 'Total MB'

PROMPT
PROMPT === LOB Space Usage ===
PROMPT

WITH lob_segs AS (
    SELECT
        owner,
        segment_name,
        SUM(bytes) AS lob_bytes
    FROM dba_segments
    WHERE segment_type LIKE 'LOB%'
    GROUP BY owner, segment_name
),
idx_segs AS (
    SELECT
        owner,
        segment_name,
        SUM(bytes) AS idx_bytes
    FROM dba_segments
    WHERE segment_type LIKE 'LOBINDEX%'
    GROUP BY owner, segment_name
)
SELECT
    l.owner,
    l.table_name,
    l.column_name,
    l.tablespace_name,
    NVL(l.securefile, 'NO') AS securefile,
    NVL(l.in_row, 'NO') AS in_row,
    NVL(l.compression, 'NONE') AS compression,
    NVL(l.deduplication, 'NONE') AS deduplication,
    NVL(l.encrypt, 'NONE') AS encryption,
    ROUND(NVL(ls.lob_bytes, 0) / 1024 / 1024, 2) AS lob_mb,
    ROUND(NVL(isg.idx_bytes, 0) / 1024 / 1024, 2) AS index_mb,
    ROUND((NVL(ls.lob_bytes, 0) + NVL(isg.idx_bytes, 0)) / 1024 / 1024, 2) AS total_mb
FROM dba_lobs l
LEFT JOIN lob_segs ls
  ON ls.owner = l.owner
 AND ls.segment_name = l.segment_name
LEFT JOIN idx_segs isg
  ON isg.owner = l.owner
 AND isg.segment_name = l.index_name
WHERE ('&&p_owner' = '%' OR l.owner = UPPER('&&p_owner'))
  AND l.table_name NOT LIKE 'BIN$%'
ORDER BY total_mb DESC, l.owner, l.table_name, l.column_name;

COLUMN owner CLEAR
COLUMN table_name CLEAR
COLUMN column_name CLEAR
COLUMN tablespace_name CLEAR
COLUMN securefile CLEAR
COLUMN in_row CLEAR
COLUMN compression CLEAR
COLUMN deduplication CLEAR
COLUMN encryption CLEAR
COLUMN lob_mb CLEAR
COLUMN index_mb CLEAR
COLUMN total_mb CLEAR

UNDEFINE p_owner
UNDEFINE 1

SET FEEDBACK ON
