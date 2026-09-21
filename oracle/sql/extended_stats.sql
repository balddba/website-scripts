/*******************************************************************************
*
* Script Name: extended_stats.sql
* Title: Extended Column Statistics
* Tags: Optimizer, Statistics
* Purpose: Lists extended column statistics and column groups from dba_stat_extensions.
*
* Description:
*   Reports user and system-created extended statistics (multi-column column
*   groups and expression statistics) recorded in DBA_STAT_EXTENSIONS for the
*   cost-based optimizer.
*
* Parameters:
*   &1 - (Optional) Schema owner filter. Default: % (all schemas)
*
* Required Privileges:
*   - SELECT on DBA_STAT_EXTENSIONS
*
* Output Format:
*   - Owner
*   - Table Name
*   - Extension Name
*   - Extension Expression / Columns
*   - Creator
*   - Droppable
*
* Example Usage:
*   sqlplus user/password@yourdb @extended_stats.sql
*   sqlplus user/password@yourdb @extended_stats.sql HR
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET LINESIZE 200
SET PAGESIZE 100
SET VERIFY OFF

COLUMN owner          FORMAT A20 HEADING 'Owner'
COLUMN table_name     FORMAT A30 HEADING 'Table Name'
COLUMN extension_name FORMAT A30 HEADING 'Extension Name'
COLUMN extension      FORMAT A50 HEADING 'Extension Expression / Columns'
COLUMN creator        FORMAT A10 HEADING 'Creator'
COLUMN droppable      FORMAT A10 HEADING 'Droppable'

SELECT
    owner,
    table_name,
    extension_name,
    extension,
    creator,
    droppable
FROM dba_stat_extensions
WHERE owner LIKE UPPER(NVL(NULLIF(CAST(TRIM('&1') AS VARCHAR2(128)), ''), '%'))
  AND table_name NOT LIKE 'BIN$%'
ORDER BY owner, table_name, extension_name;
