/*******************************************************************************
*
* Script Name: mview_refresh_groups.sql
* Title: Materialized view refresh groups
* Tags: MViews, Replication, Jobs
* Purpose: List DBMS_REFRESH groups, schedules, and child mviews
*
* Description:
*   Reports refresh groups from DBA_REFRESH (name, next date, interval,
*   broken flag, and job) and their children from DBA_REFRESH_CHILDREN
*   (child owner, name, and type). Optional filters limit the report to one
*   schema and/or one group name. Oracle-maintained schemas are omitted when
*   the schema filter is %.
*
* Parameters:
*   &1 - (Optional) Schema (group owner or child owner). Default is %.
*        Press Enter at the SQL*Plus prompt if no argument is passed.
*   &2 - (Optional) Refresh group name. Default is % (every group in scope).
*
* Required Privileges:
*   - SELECT on DBA_REFRESH
*   - SELECT on DBA_REFRESH_CHILDREN
*   - SELECT on DBA_USERS
*
* Output Format:
*   - One row per refresh group: owner, name, next date, interval, broken, job
*   - One row per child: group owner/name, child owner/name, type, schedule
*
* Example Usage:
*   SQL> @mview_refresh_groups.sql
*   SQL> @mview_refresh_groups.sql HR
*   SQL> @mview_refresh_groups.sql HR HR_GROUP
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 220
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF
SET NULL '(null)'

-- Optional &1/&2: SQL*Plus prompts if omitted; Enter means schema=% and all groups.
COLUMN c_owner NEW_VALUE p_owner NOPRINT
COLUMN c_group NEW_VALUE p_group NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), '%') AS c_owner,
       NVL(CAST(TRIM('&2') AS VARCHAR2(128)), '%') AS c_group
FROM dual;

VARIABLE rg_owner VARCHAR2(128)
VARIABLE rg_name  VARCHAR2(128)

BEGIN
    :rg_owner := UPPER(TRIM('&&p_owner'));
    :rg_name  := UPPER(TRIM('&&p_group'));

    IF :rg_owner <> '%'
       AND NOT REGEXP_LIKE(:rg_owner, '^[A-Z][A-Z0-9_$#]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Schema must be an ordinary Oracle identifier or %.'
        );
    END IF;

    IF :rg_name <> '%'
       AND NOT REGEXP_LIKE(:rg_name, '^[A-Z][A-Z0-9_$#]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Refresh group name must be an ordinary Oracle identifier or %.'
        );
    END IF;
END;
/

COLUMN rowner        FORMAT A20  HEADING 'Group Owner'
COLUMN rname         FORMAT A30  HEADING 'Group Name'
COLUMN refgroup      FORMAT 99999990 HEADING 'Refgroup'
COLUMN next_date     FORMAT A19  HEADING 'Next Date'
COLUMN interval      FORMAT A28  HEADING 'Interval'
COLUMN broken        FORMAT A6   HEADING 'Broken'
COLUMN job           FORMAT 99999990 HEADING 'Job'
COLUMN job_name      FORMAT A30  HEADING 'Job Name'
COLUMN child_count   FORMAT 9990 HEADING 'Children'
COLUMN child_owner   FORMAT A20  HEADING 'Child Owner'
COLUMN child_name    FORMAT A30  HEADING 'Child Name'
COLUMN child_type    FORMAT A18  HEADING 'Type'
COLUMN child_next    FORMAT A19  HEADING 'Child Next'
COLUMN child_interval FORMAT A28 HEADING 'Child Interval'
COLUMN child_broken  FORMAT A6   HEADING 'Broken'
COLUMN child_job     FORMAT 99999990 HEADING 'Job'

PROMPT
PROMPT === Refresh groups ===
PROMPT

SELECT
    r.rowner,
    r.rname,
    r.refgroup,
    TO_CHAR(r.next_date, 'YYYY-MM-DD HH24:MI:SS') AS next_date,
    r.interval,
    r.broken,
    r.job,
    r.job_name,
    (
        SELECT COUNT(*)
        FROM dba_refresh_children c
        WHERE c.rowner = r.rowner
          AND c.rname = r.rname
    ) AS child_count
FROM dba_refresh r
JOIN dba_users u
  ON u.username = r.rowner
WHERE (:rg_name = '%' OR r.rname = :rg_name)
  AND (:rg_owner <> '%' OR u.oracle_maintained = 'N')
  AND (
        :rg_owner = '%'
        OR r.rowner = :rg_owner
        OR EXISTS (
            SELECT 1
            FROM dba_refresh_children c
            WHERE c.rowner = r.rowner
              AND c.rname = r.rname
              AND c.owner = :rg_owner
        )
      )
ORDER BY r.rowner, r.rname;

PROMPT
PROMPT === Refresh group children ===
PROMPT

SELECT
    c.rowner,
    c.rname,
    c.owner AS child_owner,
    c.name AS child_name,
    c.type AS child_type,
    TO_CHAR(c.next_date, 'YYYY-MM-DD HH24:MI:SS') AS child_next,
    c.interval AS child_interval,
    c.broken AS child_broken,
    c.job AS child_job
FROM dba_refresh_children c
JOIN dba_users u
  ON u.username = c.rowner
WHERE (:rg_name = '%' OR c.rname = :rg_name)
  AND (:rg_owner <> '%' OR u.oracle_maintained = 'N')
  AND (
        :rg_owner = '%'
        OR c.rowner = :rg_owner
        OR c.owner = :rg_owner
      )
ORDER BY c.rowner, c.rname, c.owner, c.name;

COLUMN rowner CLEAR
COLUMN rname CLEAR
COLUMN refgroup CLEAR
COLUMN next_date CLEAR
COLUMN interval CLEAR
COLUMN broken CLEAR
COLUMN job CLEAR
COLUMN job_name CLEAR
COLUMN child_count CLEAR
COLUMN child_owner CLEAR
COLUMN child_name CLEAR
COLUMN child_type CLEAR
COLUMN child_next CLEAR
COLUMN child_interval CLEAR
COLUMN child_broken CLEAR
COLUMN child_job CLEAR

UNDEFINE p_owner
UNDEFINE p_group
UNDEFINE 1
UNDEFINE 2

SET FEEDBACK ON
SET VERIFY ON
SET NULL ''
