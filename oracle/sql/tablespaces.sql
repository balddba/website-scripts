/*******************************************************************************
*
* Script Name: tablespaces.sql
* Title: Tablespace inventory
* Tags: Capacity, Tablespaces
* Purpose: Report tablespace type, size, used bytes, and percent used including temp
*
* Description:
*   Combines permanent and locally managed temporary tablespaces into one
*   inventory, with report totals for size and used bytes.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on DBA_TABLESPACES
*   - SELECT on DBA_DATA_FILES
*   - SELECT on DBA_FREE_SPACE
*   - SELECT on DBA_TEMP_FILES
*   - SELECT on V$TEMP_EXTENT_POOL
*
* Output Format:
*   - Status, tablespace name, type, extent management
*   - Size, used bytes, percent used
*
* Example Usage:
*   @tablespaces.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET LINESIZE 130
SET NEWPAGE  0
SET PAGESIZE 66
SET VERIFY OFF
set linesize 140

COLUMN status     FORMAT a9               HEADING 'Status'
COLUMN name       FORMAT a28              HEADING 'Tablespace Name'
COLUMN type       FORMAT a12              HEADING 'TS Type'
COLUMN extent_mgt FORMAT a11              HEADING 'Extent Mgt.'
COLUMN ts_size    FORMAT 999,999,999,999  HEADING 'Tablespace Size'
COLUMN used       FORMAT 999,999,999,999  HEADING 'Used (in bytes)'
COLUMN pct_used   FORMAT 999              HEADING 'Pct. Used'

BREAK ON report
COMPUTE SUM OF ts_size  ON report
COMPUTE SUM OF used     ON report
COMPUTE AVG OF pct_used ON report

select * from (
SELECT
    d.status                                            status
  , d.tablespace_name                                   name
  , d.contents                                          type
  , d.extent_management                                 extent_mgt
  , NVL(a.bytes, 0)                                     ts_size
  , NVL(a.bytes - NVL(f.bytes, 0), 0)                   used
  , NVL((a.bytes - NVL(f.bytes, 0)) / a.bytes * 100, 0) pct_used
FROM 
    sys.dba_tablespaces d
  , ( select tablespace_name, sum(bytes) bytes
      from dba_data_files
      group by tablespace_name
    ) a
  , ( select tablespace_name, sum(bytes) bytes
      from dba_free_space
      group by tablespace_name
    ) f
WHERE
      d.tablespace_name = a.tablespace_name
  AND d.tablespace_name = f.tablespace_name
  AND NOT (
    d.extent_management like 'LOCAL'
    AND
    d.contents like 'TEMPORARY'
  )
UNION ALL 
SELECT
    d.status                         status
  , d.tablespace_name                name
  , d.contents                       type
  , d.extent_management              extent_mg
  , NVL(a.bytes, 0)                  ts_size
  , NVL(t.bytes, 0)                  used
  , NVL(t.bytes / a.bytes * 100, 0)  pct_used
FROM
    sys.dba_tablespaces d
  , ( select tablespace_name, sum(bytes) bytes
      from dba_temp_files
      group by tablespace_name
    ) a
  , ( select tablespace_name, sum(bytes_cached) bytes
      from v$temp_extent_pool
      group by tablespace_name
    ) t
WHERE
      d.tablespace_name = a.tablespace_name
  AND d.tablespace_name = t.tablespace_name
  AND d.extent_management like 'LOCAL'
  AND d.contents like 'TEMPORARY'
)
order by name
/


