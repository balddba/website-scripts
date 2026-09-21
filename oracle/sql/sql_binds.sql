/*******************************************************************************
*
* Script Name: sql_binds.sql
* Title: SQL Bind Values
* Tags: Performance, SQL Tuning, Binds
* Purpose: Captured bind variable values for a SQL_ID from gv$sql_bind_capture and dba_hist_sqlbind (optional &1 for SQL_ID, defaults to '%').
*
* Description:
*   Displays captured bind variable values, datatypes, and capture timestamps
*   from memory (GV$SQL_BIND_CAPTURE) and historical AWR snapshots
*   (DBA_HIST_SQLBIND). Filters by SQL_ID if provided, or lists recent captured
*   binds across all statements.
*
* Parameters:
*   &1 - (Optional) SQL_ID. Default is '%' (all captured bind variables).
*
* Required Privileges:
*   - SELECT on GV$SQL_BIND_CAPTURE
*   - SELECT on DBA_HIST_SQLBIND
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - In-memory binds: instance ID, SQL ID, child number, position, name, datatype, value, capture time
*   - Historical binds: snapshot ID, instance ID, SQL ID, position, name, datatype, value, capture time
*
* Example Usage:
*   sqlplus user/password@yourdb @sql_binds.sql
*   sqlplus user/password@yourdb @sql_binds.sql 8zxfktj5s7k8m
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

COLUMN c_sqlid NEW_VALUE p_sqlid NOPRINT
SELECT NVL(NULLIF(TRIM('&1'), ''), '%') AS c_sqlid FROM dual;

COLUMN inst_id         FORMAT 999              HEADING 'Inst'
COLUMN snap_id         FORMAT 99999999         HEADING 'Snap ID'
COLUMN sql_id          FORMAT A13              HEADING 'SQL ID'
COLUMN child_number    FORMAT 9999             HEADING 'Child'
COLUMN position        FORMAT 9999             HEADING 'Pos'
COLUMN name            FORMAT A15              HEADING 'Bind Name'
COLUMN datatype_string FORMAT A15              HEADING 'Data Type'
COLUMN value_string    FORMAT A40 TRUNC        HEADING 'Value'
COLUMN was_captured    FORMAT A3               HEADING 'Cap'
COLUMN last_captured   FORMAT A19              HEADING 'Last Captured'

PROMPT
PROMPT === In-Memory Bind Capture (GV$SQL_BIND_CAPTURE) ===
PROMPT

SELECT
    b.inst_id,
    b.sql_id,
    b.child_number,
    b.position,
    b.name,
    b.datatype_string,
    b.value_string,
    b.was_captured,
    TO_CHAR(b.last_captured, 'YYYY-MM-DD HH24:MI:SS') AS last_captured
FROM gv$sql_bind_capture b
WHERE b.sql_id LIKE '&&p_sqlid'
ORDER BY b.inst_id, b.sql_id, b.child_number, b.position;

PROMPT
PROMPT === Historical Bind Capture (DBA_HIST_SQLBIND) ===
PROMPT

SELECT
    h.snap_id,
    h.instance_number AS inst_id,
    h.sql_id,
    h.position,
    h.name,
    h.datatype_string,
    h.value_string,
    h.was_captured,
    TO_CHAR(h.last_captured, 'YYYY-MM-DD HH24:MI:SS') AS last_captured
FROM dba_hist_sqlbind h
WHERE h.sql_id LIKE '&&p_sqlid'
ORDER BY h.snap_id DESC, h.instance_number, h.sql_id, h.position;

COLUMN inst_id CLEAR
COLUMN snap_id CLEAR
COLUMN sql_id CLEAR
COLUMN child_number CLEAR
COLUMN position CLEAR
COLUMN name CLEAR
COLUMN datatype_string CLEAR
COLUMN value_string CLEAR
COLUMN was_captured CLEAR
COLUMN last_captured CLEAR
COLUMN c_sqlid CLEAR

UNDEFINE p_sqlid
UNDEFINE 1

SET FEEDBACK ON
SET VERIFY ON
