/*******************************************************************************
*
* Script Name: licensing.sql
* Title: Oracle licensing snapshot
* Tags: Licensing, Options
* Purpose: Snapshot edition, CPU/session license view, installed options in use, and currently used features
*
* Description:
*   High-level licensing snapshot for the current database. Complements
*   installed_options.sql (full V$OPTION inventory) and feature_usage.sql
*   (detection history). This script shows version and edition, CPU and
*   session figures from V$LICENSE and V$OSSTAT, options whose V$OPTION
*   value is TRUE, and features with CURRENTLY_USED = TRUE. SESSIONS_MAX
*   of zero means named-user licensing rather than concurrent-session
*   licensing. This is an inventory aid, not a license entitlement report.
*   Run it in the container you care about (CDB root or a PDB).
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$VERSION
*   - SELECT on V$INSTANCE
*   - SELECT on V$DATABASE
*   - SELECT on V$LICENSE
*   - SELECT on V$PARAMETER
*   - SELECT on V$OSSTAT
*   - SELECT on V$OPTION
*   - SELECT on DBA_FEATURE_USAGE_STATISTICS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Database version, edition, name, and role
*   - Session and CPU license view
*   - Installed options that are TRUE
*   - Features currently marked in use
*
* Example Usage:
*   SQL> @licensing.sql
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

COLUMN metric            FORMAT A36              HEADING 'Metric'
COLUMN value             FORMAT A80              HEADING 'Value'
COLUMN parameter         FORMAT A55              HEADING 'Option'
COLUMN option_value      FORMAT A10              HEADING 'Installed'
COLUMN name              FORMAT A55              HEADING 'Feature'
COLUMN currently_used    FORMAT A8               HEADING 'In Use'
COLUMN version           FORMAT A17              HEADING 'Version'

PROMPT
PROMPT === Version and edition ===
PROMPT

SELECT metric, value
FROM (
    SELECT 10 AS n, 'banner' AS metric, banner AS value
    FROM v$version
    WHERE banner LIKE 'Oracle Database%'
      AND ROWNUM = 1
    UNION ALL
    SELECT 20, 'instance_name', instance_name FROM v$instance
    UNION ALL
    SELECT 30, 'version', version FROM v$instance
    UNION ALL
    SELECT 40, 'edition',
           NVL(edition, '(see banner; EDITION not in this V$INSTANCE)')
    FROM v$instance
    UNION ALL
    SELECT 50, 'db_name', name FROM v$database
    UNION ALL
    SELECT 60, 'db_unique_name', db_unique_name FROM v$database
    UNION ALL
    SELECT 70, 'database_role', database_role FROM v$database
    UNION ALL
    SELECT 80, 'cdb', cdb FROM v$database
    UNION ALL
    SELECT 90, 'open_mode', open_mode FROM v$database
)
ORDER BY n;

PROMPT
PROMPT === Session and CPU license view ===
PROMPT
PROMPT V$LICENSE.SESSIONS_MAX = 0 means named-user licensing (concurrent
PROMPT session limits are not enabled). CPU_COUNT is the instance parameter;
PROMPT cores and sockets come from V$OSSTAT.

SELECT metric, value
FROM (
    SELECT 10 AS n, 'license_mode' AS metric,
           CASE
               WHEN sessions_max = 0 THEN 'NAMED USER (sessions_max=0)'
               ELSE 'CONCURRENT SESSION (sessions_max=' || TO_CHAR(sessions_max) || ')'
           END AS value
    FROM v$license
    UNION ALL
    SELECT 20, 'sessions_max', TO_CHAR(sessions_max) FROM v$license
    UNION ALL
    SELECT 30, 'sessions_warning', TO_CHAR(sessions_warning) FROM v$license
    UNION ALL
    SELECT 40, 'sessions_current', TO_CHAR(sessions_current) FROM v$license
    UNION ALL
    SELECT 50, 'sessions_highwater', TO_CHAR(sessions_highwater) FROM v$license
    UNION ALL
    SELECT 60, 'users_max', TO_CHAR(users_max) FROM v$license
    UNION ALL
    SELECT 70, 'cpu_count_current', TO_CHAR(cpu_count_current) FROM v$license
    UNION ALL
    SELECT 80, 'cpu_count_highwater', TO_CHAR(cpu_count_highwater) FROM v$license
    UNION ALL
    SELECT 90, 'cpu_count', NVL(display_value, value)
    FROM v$parameter
    WHERE name = 'cpu_count'
    UNION ALL
    SELECT 100, LOWER(stat_name), TO_CHAR(value)
    FROM v$osstat
    WHERE stat_name IN ('NUM_CPUS', 'NUM_CPU_CORES', 'NUM_CPU_SOCKETS')
)
ORDER BY n, metric;

PROMPT
PROMPT === Options installed (V$OPTION = TRUE) ===
PROMPT
PROMPT Full TRUE/FALSE inventory: @installed_options.sql

SELECT
    parameter,
    value AS option_value
FROM v$option
WHERE value = 'TRUE'
ORDER BY parameter;

PROMPT
PROMPT === Features currently used ===
PROMPT
PROMPT Detection history and first/last dates: @feature_usage.sql

SELECT
    u.name,
    u.currently_used,
    u.version
FROM dba_feature_usage_statistics u
WHERE u.dbid = (SELECT dbid FROM v$database)
  AND u.currently_used = 'TRUE'
  AND u.version = (
        SELECT MAX(u2.version)
        FROM dba_feature_usage_statistics u2
        WHERE u2.name = u.name
          AND u2.dbid = u.dbid
      )
ORDER BY u.name;

COLUMN metric CLEAR
COLUMN value CLEAR
COLUMN parameter CLEAR
COLUMN option_value CLEAR
COLUMN name CLEAR
COLUMN currently_used CLEAR
COLUMN version CLEAR

SET FEEDBACK ON
SET VERIFY ON
