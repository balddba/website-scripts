/*******************************************************************************
*
* Script Name: mviews.sql
* Title: Materialized views and mview logs
* Tags: MViews, Replication
* Purpose: Report materialized views and their logs by schema or by name
*
* Description:
*   Lists DBA_MVIEWS rows for a schema (or one named mview) with container,
*   query rewrite, refresh mode and method, last refresh, staleness, and
*   compile state. Matching DBA_MVIEW_LOGS rows follow. When a mview name is
*   given, the report also prints that mview's query text and any logs on its
*   master tables (DBA_MVIEW_DETAIL_RELATIONS). Oracle-maintained schemas are
*   omitted when owner is %.
*
* Parameters:
*   &1 - (Optional) Owner. Default is % (every non-Oracle-maintained schema).
*        Press Enter at the SQL*Plus prompt if no argument is passed.
*   &2 - (Optional) Materialized view name. Default is % (every mview in scope).
*        When set, that mview is listed with its query and related logs.
*
* Required Privileges:
*   - SELECT on DBA_MVIEWS
*   - SELECT on DBA_MVIEW_LOGS
*   - SELECT on DBA_MVIEW_DETAIL_RELATIONS
*   - SELECT on DBA_USERS
*
* Output Format:
*   - One row per materialized view: owner, name, container, rewrite,
*     refresh mode/method, last refresh, staleness, compile state
*   - Query text when a specific mview name is supplied
*   - One row per matching mview log: log owner, master, log table, rowids,
*     primary key, sequence, filter columns, including new values
*
* Example Usage:
*   SQL> @mviews.sql
*   SQL> @mviews.sql HR
*   SQL> @mviews.sql HR MV_EMP
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 240
SET PAGESIZE 100
SET LONG 4000
SET LONGCHUNKSIZE 4000
SET TRIMSPOOL ON
SET TAB OFF
SET NULL '(null)'

-- Optional &1/&2: SQL*Plus prompts if omitted; Enter means owner=% and all names.
COLUMN c_owner NEW_VALUE p_owner NOPRINT
COLUMN c_name  NEW_VALUE p_name  NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), '%') AS c_owner,
       NVL(CAST(TRIM('&2') AS VARCHAR2(128)), '%') AS c_name
FROM dual;

VARIABLE mv_owner VARCHAR2(128)
VARIABLE mv_name  VARCHAR2(128)

BEGIN
    :mv_owner := UPPER(TRIM('&&p_owner'));
    :mv_name  := UPPER(TRIM('&&p_name'));

    IF :mv_owner <> '%'
       AND NOT REGEXP_LIKE(:mv_owner, '^[A-Z][A-Z0-9_$#]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Owner must be an ordinary Oracle identifier or %.'
        );
    END IF;

    IF :mv_name <> '%'
       AND NOT REGEXP_LIKE(:mv_name, '^[A-Z][A-Z0-9_$#]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Mview name must be an ordinary Oracle identifier or %.'
        );
    END IF;
END;
/

COLUMN owner            FORMAT A20  HEADING 'Owner'
COLUMN mview_name       FORMAT A30  HEADING 'Mview Name'
COLUMN container_name   FORMAT A30  HEADING 'Container'
COLUMN rewrite_enabled  FORMAT A7   HEADING 'Rewrite'
COLUMN refresh_mode     FORMAT A10  HEADING 'Ref Mode'
COLUMN refresh_method   FORMAT A10  HEADING 'Ref Method'
COLUMN last_refresh     FORMAT A19  HEADING 'Last Refresh'
COLUMN staleness        FORMAT A14  HEADING 'Staleness'
COLUMN compile_state    FORMAT A18  HEADING 'Compile State'
COLUMN query_text       FORMAT A120 HEADING 'Query'
COLUMN log_owner        FORMAT A20  HEADING 'Log Owner'
COLUMN master           FORMAT A30  HEADING 'Master'
COLUMN log_table        FORMAT A30  HEADING 'Log Table'
COLUMN rowids           FORMAT A6   HEADING 'Rowids'
COLUMN primary_key      FORMAT A6   HEADING 'PK'
COLUMN sequence         FORMAT A6   HEADING 'Seq'
COLUMN filter_columns   FORMAT A7   HEADING 'Filter'
COLUMN include_new_values FORMAT A8 HEADING 'New Vals'

PROMPT
PROMPT === Materialized views ===
PROMPT

SELECT
    m.owner,
    m.mview_name,
    m.container_name,
    m.rewrite_enabled,
    m.refresh_mode,
    m.refresh_method,
    TO_CHAR(m.last_refresh_date, 'YYYY-MM-DD HH24:MI:SS') AS last_refresh,
    m.staleness,
    m.compile_state
FROM dba_mviews m
JOIN dba_users u
  ON u.username = m.owner
WHERE (:mv_owner = '%' OR m.owner = :mv_owner)
  AND (:mv_name = '%' OR m.mview_name = :mv_name)
  AND (:mv_owner <> '%' OR u.oracle_maintained = 'N')
ORDER BY m.owner, m.mview_name;

PROMPT
PROMPT === Query text (named mview only) ===
PROMPT

SELECT
    m.owner,
    m.mview_name,
    m.query AS query_text
FROM dba_mviews m
JOIN dba_users u
  ON u.username = m.owner
WHERE :mv_name <> '%'
  AND (:mv_owner = '%' OR m.owner = :mv_owner)
  AND m.mview_name = :mv_name
  AND (:mv_owner <> '%' OR u.oracle_maintained = 'N')
ORDER BY m.owner, m.mview_name;

PROMPT
PROMPT === Materialized view logs ===
PROMPT

SELECT
    l.log_owner,
    l.master,
    l.log_table,
    l.rowids,
    l.primary_key,
    l.sequence,
    l.filter_columns,
    l.include_new_values
FROM dba_mview_logs l
JOIN dba_users u
  ON u.username = l.log_owner
WHERE (:mv_owner = '%' OR l.log_owner = :mv_owner)
  AND (:mv_owner <> '%' OR u.oracle_maintained = 'N')
  AND (
        :mv_name = '%'
        OR l.master = :mv_name
        OR l.log_table = :mv_name
        OR EXISTS (
            SELECT 1
            FROM dba_mview_detail_relations d
            WHERE (:mv_owner = '%' OR d.owner = :mv_owner)
              AND d.mview_name = :mv_name
              AND d.detailobj_owner = l.log_owner
              AND d.detailobj_name = l.master
        )
      )
ORDER BY l.log_owner, l.master, l.log_table;

COLUMN owner CLEAR
COLUMN mview_name CLEAR
COLUMN container_name CLEAR
COLUMN rewrite_enabled CLEAR
COLUMN refresh_mode CLEAR
COLUMN refresh_method CLEAR
COLUMN last_refresh CLEAR
COLUMN staleness CLEAR
COLUMN compile_state CLEAR
COLUMN query_text CLEAR
COLUMN log_owner CLEAR
COLUMN master CLEAR
COLUMN log_table CLEAR
COLUMN rowids CLEAR
COLUMN primary_key CLEAR
COLUMN sequence CLEAR
COLUMN filter_columns CLEAR
COLUMN including_new_values CLEAR

UNDEFINE p_owner
UNDEFINE p_name
UNDEFINE 1
UNDEFINE 2

SET FEEDBACK ON
SET VERIFY ON
SET NULL ''
