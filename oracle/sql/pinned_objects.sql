/*******************************************************************************
*
* Script Name: pinned_objects.sql
* Title: Pinned shared pool objects
* Tags: Memory, Shared Pool, SGA
* Purpose: List objects pinned in the shared pool (KEPT) with size, loads, executions, locks, and pins
*
* Description:
*   Reports objects in V$DB_OBJECT_CACHE with KEPT = YES. That flag is set by
*   DBMS_SHARED_POOL.KEEP (or equivalent) so the object stays in the shared
*   pool instead of aging out. SHARABLE_MEM is the current memory for that
*   cached object. High LOADS with KEPT = YES usually means the object was
*   kept after it had already been flushed. This is the shared-pool keep
*   list, not the KEEP buffer pool. OWNER is null for some cursor rows.
*
* Parameters:
*   &1 - (Optional) Owner to filter (case-insensitive). Default is all owners.
*        Press Enter at the SQL*Plus prompt if no argument is passed.
*
* Required Privileges:
*   - SELECT on V$DB_OBJECT_CACHE
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Count and total sharable memory of kept objects
*   - Kept memory by object type
*   - One row per kept object: owner, name, type, memory, loads, executions,
*     locks, pins, invalidations, and status
*
* Example Usage:
*   SQL> @pinned_objects.sql
*   SQL> @pinned_objects.sql SYS
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

-- Optional &1: SQL*Plus prompts if omitted; Enter (empty) means all owners.
COLUMN c_owner NEW_VALUE p_owner NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), '%') AS c_owner FROM dual;

COLUMN kept_count     FORMAT 999,999           HEADING 'Kept Count'
COLUMN kept_mb        FORMAT 999,999,990.00    HEADING 'Kept MB'
COLUMN object_type    FORMAT A24               HEADING 'Type'
COLUMN type_count     FORMAT 999,999           HEADING 'Count'
COLUMN owner          FORMAT A24               HEADING 'Owner'
COLUMN name           FORMAT A50 TRUNC         HEADING 'Name'
COLUMN type           FORMAT A24               HEADING 'Type'
COLUMN namespace      FORMAT A18 TRUNC         HEADING 'Namespace'
COLUMN sharable_mb    FORMAT 999,990.00        HEADING 'Sharable MB'
COLUMN sharable_bytes FORMAT 999,999,999,990   HEADING 'Sharable Bytes'
COLUMN loads          FORMAT 999,999,990       HEADING 'Loads'
COLUMN executions     FORMAT 999,999,999,990   HEADING 'Executions'
COLUMN locks          FORMAT 999,999,990       HEADING 'Locks'
COLUMN pins           FORMAT 999,999,990       HEADING 'Pins'
COLUMN invalidations  FORMAT 999,999,990       HEADING 'Invals'
COLUMN status         FORMAT A12               HEADING 'Status'

PROMPT
PROMPT === Kept object summary ===
PROMPT

SELECT
    COUNT(*) AS kept_count,
    ROUND(SUM(sharable_mem) / 1024 / 1024, 2) AS kept_mb
FROM v$db_object_cache
WHERE kept = 'YES'
  AND NVL(owner, '%') LIKE UPPER('&&p_owner');

PROMPT
PROMPT === Kept memory by type ===
PROMPT

SELECT
    type AS object_type,
    COUNT(*) AS type_count,
    ROUND(SUM(sharable_mem) / 1024 / 1024, 2) AS kept_mb
FROM v$db_object_cache
WHERE kept = 'YES'
  AND NVL(owner, '%') LIKE UPPER('&&p_owner')
GROUP BY type
ORDER BY SUM(sharable_mem) DESC, type;

PROMPT
PROMPT === Kept objects ===
PROMPT

SELECT
    NVL(owner, '(none)') AS owner,
    name,
    type,
    namespace,
    ROUND(sharable_mem / 1024 / 1024, 2) AS sharable_mb,
    sharable_mem AS sharable_bytes,
    loads,
    executions,
    locks,
    pins,
    invalidations,
    status
FROM v$db_object_cache
WHERE kept = 'YES'
  AND NVL(owner, '%') LIKE UPPER('&&p_owner')
ORDER BY sharable_mem DESC, owner, name;

COLUMN c_owner CLEAR
COLUMN kept_count CLEAR
COLUMN kept_mb CLEAR
COLUMN object_type CLEAR
COLUMN type_count CLEAR
COLUMN owner CLEAR
COLUMN name CLEAR
COLUMN type CLEAR
COLUMN namespace CLEAR
COLUMN sharable_mb CLEAR
COLUMN sharable_bytes CLEAR
COLUMN loads CLEAR
COLUMN executions CLEAR
COLUMN locks CLEAR
COLUMN pins CLEAR
COLUMN invalidations CLEAR
COLUMN status CLEAR

SET FEEDBACK ON
SET VERIFY ON
