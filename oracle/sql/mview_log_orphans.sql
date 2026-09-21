/*******************************************************************************
*
* Script Name: mview_log_orphans.sql
* Title: Orphaned mview log registrations
* Tags: MViews, Replication, Diagnostics
* Purpose: Identify orphaned snapshot registrations and unused mview logs
*
* Description:
*   Display-only report of classic orphaned snapshot / site leftovers on the
*   master: mview logs with no registered subscribers, SYS.SLOG$ snapids that
*   are not in DBA_REGISTERED_MVIEWS / DBA_REGISTERED_SNAPSHOTS, registrations
*   with no SLOG$ row, local-site registrations whose mview no longer exists,
*   and leftover SNAPTIME% columns on log tables (besides SNAPTIME$$).
*   This script does not unregister snapshots or drop logs.
*
* Parameters:
*   &1 - (Optional) Master / log owner. Default is % (every non-Oracle-
*        maintained schema). Press Enter at the SQL*Plus prompt if omitted.
*
* Required Privileges:
*   - SELECT on DBA_MVIEW_LOGS
*   - SELECT on DBA_REGISTERED_MVIEWS
*   - SELECT on DBA_REGISTERED_SNAPSHOTS
*   - SELECT on DBA_BASE_TABLE_MVIEWS
*   - SELECT on DBA_MVIEWS
*   - SELECT on DBA_TAB_COLUMNS
*   - SELECT on DBA_USERS
*   - SELECT on SYS.SLOG$
*   - SELECT on SYS.MLOG$
*   - SELECT on GLOBAL_NAME
*
* Output Format:
*   - Mview logs with no registered snapshots / SLOG$ subscribers
*   - SLOG$ subscribers whose snapid is not registered
*   - Registered mviews / snapshots with no SLOG$ row
*   - Local-site registrations with no matching DBA_MVIEWS row
*   - Extra SNAPTIME% columns on mview log tables
*
* Example Usage:
*   SQL> @mview_log_orphans.sql
*   SQL> @mview_log_orphans.sql HR
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
SET NULL '(null)'

-- Optional &1: SQL*Plus prompts if omitted; Enter (empty) means all user schemas.
COLUMN c_owner NEW_VALUE p_owner NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), '%') AS c_owner FROM dual;

VARIABLE log_owner VARCHAR2(128)

BEGIN
    :log_owner := UPPER(TRIM('&&p_owner'));

    IF :log_owner <> '%'
       AND NOT REGEXP_LIKE(:log_owner, '^[A-Z][A-Z0-9_$#]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Owner must be an ordinary Oracle identifier or %.'
        );
    END IF;
END;
/

COLUMN log_owner       FORMAT A20  HEADING 'Log Owner'
COLUMN master          FORMAT A30  HEADING 'Master'
COLUMN log_table       FORMAT A30  HEADING 'Log Table'
COLUMN rowids          FORMAT A6   HEADING 'Rowids'
COLUMN primary_key     FORMAT A6   HEADING 'PK'
COLUMN mowner          FORMAT A20  HEADING 'Master Owner'
COLUMN snapid          FORMAT 9999999990 HEADING 'Snap ID'
COLUMN snaptime        FORMAT A19  HEADING 'Snaptime'
COLUMN youngest        FORMAT A19  HEADING 'MLOG Youngest'
COLUMN oldest          FORMAT A19  HEADING 'MLOG Oldest'
COLUMN mview_owner     FORMAT A20  HEADING 'Mview Owner'
COLUMN mview_name      FORMAT A30  HEADING 'Mview Name'
COLUMN mview_site      FORMAT A40  HEADING 'Site'
COLUMN column_name     FORMAT A30  HEADING 'Column'
COLUMN data_type       FORMAT A15  HEADING 'Type'
COLUMN problem         FORMAT A48  HEADING 'Problem'

PROMPT
PROMPT === DISPLAY ONLY: do not DELETE or UNREGISTER from this script ===
PROMPT
PROMPT === Mview logs with no registered snapshots ===
PROMPT

SELECT
    l.log_owner,
    l.master,
    l.log_table,
    l.rowids,
    l.primary_key,
    'NO REGISTERED SNAPSHOTS OR SLOG$ ROWS' AS problem
FROM dba_mview_logs l
JOIN dba_users u
  ON u.username = l.log_owner
WHERE (:log_owner = '%' OR l.log_owner = :log_owner)
  AND (:log_owner <> '%' OR u.oracle_maintained = 'N')
  AND NOT EXISTS (
        SELECT 1
        FROM dba_base_table_mviews b
        WHERE b.owner = l.log_owner
          AND b.master = l.master
      )
  AND NOT EXISTS (
        SELECT 1
        FROM sys.slog$ s
        WHERE s.mowner = l.log_owner
          AND s.master = l.master
      )
ORDER BY l.log_owner, l.master;

PROMPT
PROMPT === SLOG$ subscribers with no matching registration ===
PROMPT

SELECT
    s.mowner,
    s.master,
    s.snapid,
    TO_CHAR(s.snaptime, 'YYYY-MM-DD HH24:MI:SS') AS snaptime,
    TO_CHAR(m.youngest, 'YYYY-MM-DD HH24:MI:SS') AS youngest,
    TO_CHAR(m.oldest, 'YYYY-MM-DD HH24:MI:SS') AS oldest,
    'SLOG$ SNAPID NOT IN REGISTERED MVIEWS/SNAPSHOTS' AS problem
FROM sys.slog$ s
LEFT JOIN sys.mlog$ m
  ON m.mowner = s.mowner
 AND m.master = s.master
JOIN dba_users u
  ON u.username = s.mowner
WHERE (:log_owner = '%' OR s.mowner = :log_owner)
  AND (:log_owner <> '%' OR u.oracle_maintained = 'N')
  AND NOT EXISTS (
        SELECT 1
        FROM dba_registered_mviews r
        WHERE r.mview_id = s.snapid
      )
  AND NOT EXISTS (
        SELECT 1
        FROM dba_registered_snapshots r
        WHERE r.snapshot_id = s.snapid
      )
ORDER BY s.mowner, s.master, s.snapid;

PROMPT
PROMPT === Registrations with no SLOG$ subscriber row ===
PROMPT

SELECT
    r.mview_owner,
    r.mview_name,
    r.mview_site,
    r.snapid,
    'REGISTRATION HAS NO SLOG$ ROW' AS problem
FROM (
    SELECT
        owner AS mview_owner,
        name AS mview_name,
        mview_site,
        mview_id AS snapid
    FROM dba_registered_mviews
    UNION
    SELECT
        owner,
        name,
        snapshot_site,
        snapshot_id
    FROM dba_registered_snapshots
) r
WHERE NOT EXISTS (
        SELECT 1
        FROM sys.slog$ s
        WHERE s.snapid = r.snapid
      )
  AND (
        :log_owner = '%'
        OR EXISTS (
            SELECT 1
            FROM dba_base_table_mviews b
            WHERE b.mview_id = r.snapid
              AND b.owner = :log_owner
        )
      )
ORDER BY r.mview_owner, r.mview_name, r.mview_site;

PROMPT
PROMPT === Local-site registrations with no matching mview ===
PROMPT

SELECT
    r.mview_owner,
    r.mview_name,
    r.mview_site,
    r.snapid,
    'LOCAL SITE REGISTRATION HAS NO DBA_MVIEWS ROW' AS problem
FROM (
    SELECT
        owner AS mview_owner,
        name AS mview_name,
        mview_site,
        mview_id AS snapid
    FROM dba_registered_mviews
    UNION
    SELECT
        owner,
        name,
        snapshot_site,
        snapshot_id
    FROM dba_registered_snapshots
) r
WHERE (:log_owner = '%' OR r.mview_owner = :log_owner)
  AND UPPER(r.mview_site) IN (
        SELECT UPPER(global_name) FROM global_name
        UNION ALL
        SELECT UPPER(name) FROM v$database
        UNION ALL
        SELECT UPPER(db_unique_name) FROM v$database
        UNION ALL
        SELECT UPPER(SUBSTR(global_name, 1, INSTR(global_name || '.', '.') - 1))
        FROM global_name
      )
  AND NOT EXISTS (
        SELECT 1
        FROM dba_mviews m
        WHERE m.owner = r.mview_owner
          AND m.mview_name = r.mview_name
      )
ORDER BY r.mview_owner, r.mview_name;

PROMPT
PROMPT === Leftover SNAPTIME columns on mview log tables ===
PROMPT

SELECT
    l.log_owner,
    l.master,
    l.log_table,
    c.column_name,
    c.data_type,
    'EXTRA SNAPTIME COLUMN ON MVIEW LOG' AS problem
FROM dba_mview_logs l
JOIN dba_tab_columns c
  ON c.owner = l.log_owner
 AND c.table_name = l.log_table
JOIN dba_users u
  ON u.username = l.log_owner
WHERE (:log_owner = '%' OR l.log_owner = :log_owner)
  AND (:log_owner <> '%' OR u.oracle_maintained = 'N')
  AND c.column_name LIKE 'SNAPTIME%'
  AND c.column_name <> 'SNAPTIME$$'
ORDER BY l.log_owner, l.master, c.column_name;

COLUMN log_owner CLEAR
COLUMN master CLEAR
COLUMN log_table CLEAR
COLUMN rowids CLEAR
COLUMN primary_key CLEAR
COLUMN mowner CLEAR
COLUMN snapid CLEAR
COLUMN snaptime CLEAR
COLUMN youngest CLEAR
COLUMN oldest CLEAR
COLUMN mview_owner CLEAR
COLUMN mview_name CLEAR
COLUMN mview_site CLEAR
COLUMN column_name CLEAR
COLUMN data_type CLEAR
COLUMN problem CLEAR

UNDEFINE p_owner
UNDEFINE 1

SET FEEDBACK ON
SET VERIFY ON
SET NULL ''
