/*******************************************************************************
*
* Script Name: shared_pool.sql
* Title: Shared pool
* Tags: Memory, Shared Pool
* Purpose: Report shared pool breakdown, size advice, library cache hit/reload signals, and top SQL by sharable memory
*
* Description:
*   Breaks V$SGASTAT for the shared pool (including free memory), shows
*   V$SHARED_POOL_ADVICE, and lists V$LIBRARYCACHE gets, pins, reloads,
*   and invalidations. A reload ratio above about 1 percent is a classic
*   undersized-pool signal. Top V$SQLAREA rows by SHARABLE_MEM show which
*   cursors occupy the pool; high VERSION_COUNT or LOADS on those rows
*   points at invalidation or child-cursor growth rather than raw size.
*
* Parameters:
*   &1 - (Optional) Number of top SQLAREA consumers to list. Default 20.
*        Press Enter at the SQL*Plus prompt if no argument is passed.
*
* Required Privileges:
*   - SELECT on V$PARAMETER
*   - SELECT on V$SGASTAT
*   - SELECT on V$SHARED_POOL_ADVICE
*   - SELECT on V$LIBRARYCACHE
*   - SELECT on V$SQLAREA
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - SHARED_POOL_SIZE and related parameters
*   - Shared pool V$SGASTAT rows (MB) with free memory first
*   - Shared pool size advice
*   - Library cache namespace hits, reloads, and invalidations
*   - Reload and invalidation totals
*   - Top SQL by sharable memory
*
* Example Usage:
*   SQL> @shared_pool.sql
*   SQL> @shared_pool.sql 30
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

-- Optional &1: SQL*Plus prompts if omitted; Enter (empty) means top 20.
COLUMN c_top NEW_VALUE p_top NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), '20') AS c_top FROM dual;

COLUMN parameter            FORMAT A36               HEADING 'Parameter'
COLUMN display_value        FORMAT A40               HEADING 'Value'
COLUMN pool                 FORMAT A16               HEADING 'Pool'
COLUMN name                 FORMAT A40 TRUNC         HEADING 'Name'
COLUMN bytes                FORMAT 999,999,999,990   HEADING 'Bytes'
COLUMN size_mb              FORMAT 999,999,990.00    HEADING 'MB'
COLUMN pct_of_pool          FORMAT 990.00            HEADING 'Pct'
COLUMN sp_size_mb           FORMAT 999,999,990.00    HEADING 'Size MB'
COLUMN size_factor          FORMAT 990.00            HEADING 'Factor'
COLUMN estd_lc_mb           FORMAT 999,999,990.00    HEADING 'Estd LC MB'
COLUMN estd_lc_objects      FORMAT 999,999,990       HEADING 'Estd LC Objs'
COLUMN estd_lc_time_saved   FORMAT 999,999,999,990   HEADING 'Estd Time Saved'
COLUMN estd_time_factor     FORMAT 990.00            HEADING 'Time Factor'
COLUMN namespace            FORMAT A20               HEADING 'Namespace'
COLUMN gets                 FORMAT 999,999,999,990   HEADING 'Gets'
COLUMN gethits              FORMAT 999,999,999,990   HEADING 'Get Hits'
COLUMN get_hit_pct          FORMAT 990.00            HEADING 'Get Hit %'
COLUMN pins                 FORMAT 999,999,999,990   HEADING 'Pins'
COLUMN pinhits              FORMAT 999,999,999,990   HEADING 'Pin Hits'
COLUMN pin_hit_pct          FORMAT 990.00            HEADING 'Pin Hit %'
COLUMN reloads              FORMAT 999,999,990       HEADING 'Reloads'
COLUMN invalidations        FORMAT 999,999,990       HEADING 'Invals'
COLUMN reload_pct           FORMAT 990.000           HEADING 'Reload %'
COLUMN sql_id               FORMAT A13               HEADING 'SQL ID'
COLUMN parsing_schema       FORMAT A24               HEADING 'Schema'
COLUMN sharable_mb          FORMAT 999,990.00        HEADING 'Sharable MB'
COLUMN version_count        FORMAT 999,999           HEADING 'Versions'
COLUMN executions           FORMAT 999,999,999,990   HEADING 'Executions'
COLUMN loads                FORMAT 999,999,990       HEADING 'Loads'
COLUMN sql_text             FORMAT A60 TRUNC         HEADING 'SQL Text'

PROMPT
PROMPT === Shared pool parameters ===
PROMPT

SELECT
    name AS parameter,
    NVL(display_value, '(not set)') AS display_value
FROM v$parameter
WHERE name IN (
    'shared_pool_size',
    'shared_pool_reserved_size',
    'sga_target',
    'memory_target'
)
ORDER BY name;

PROMPT
PROMPT === Shared pool breakdown (V$SGASTAT) ===
PROMPT

SELECT
    pool,
    name,
    bytes,
    ROUND(bytes / 1024 / 1024, 2) AS size_mb,
    ROUND(
        bytes / NULLIF(SUM(bytes) OVER (), 0) * 100,
        2
    ) AS pct_of_pool
FROM v$sgastat
WHERE pool = 'shared pool'
ORDER BY
    CASE WHEN name = 'free memory' THEN 0 ELSE 1 END,
    bytes DESC,
    name;

PROMPT
PROMPT === Shared pool advice ===
PROMPT

SELECT
    shared_pool_size_for_estimate AS sp_size_mb,
    shared_pool_size_factor AS size_factor,
    ROUND(estd_lc_size / 1024 / 1024, 2) AS estd_lc_mb,
    estd_lc_memory_objects AS estd_lc_objects,
    estd_lc_time_saved,
    estd_lc_time_saved_factor AS estd_time_factor
FROM v$shared_pool_advice
ORDER BY shared_pool_size_for_estimate;

PROMPT
PROMPT === Library cache ===
PROMPT

SELECT
    namespace,
    gets,
    gethits,
    ROUND(gethitratio * 100, 2) AS get_hit_pct,
    pins,
    pinhits,
    ROUND(pinhitratio * 100, 2) AS pin_hit_pct,
    reloads,
    invalidations,
    ROUND(reloads / NULLIF(pins, 0) * 100, 3) AS reload_pct
FROM v$librarycache
ORDER BY namespace;

PROMPT
PROMPT === Reload and invalidation totals ===
PROMPT

SELECT
    SUM(pins) AS pins,
    SUM(reloads) AS reloads,
    SUM(invalidations) AS invalidations,
    ROUND(SUM(reloads) / NULLIF(SUM(pins), 0) * 100, 3) AS reload_pct
FROM v$librarycache;

PROMPT
PROMPT === Top SQL by sharable memory ===
PROMPT

SELECT *
FROM (
    SELECT
        sql_id,
        parsing_schema_name AS parsing_schema,
        ROUND(sharable_mem / 1024 / 1024, 2) AS sharable_mb,
        version_count,
        executions,
        loads,
        invalidations,
        sql_text
    FROM v$sqlarea
    ORDER BY sharable_mem DESC NULLS LAST
)
WHERE ROWNUM <= TO_NUMBER('&&p_top');

COLUMN c_top CLEAR
COLUMN parameter CLEAR
COLUMN display_value CLEAR
COLUMN pool CLEAR
COLUMN name CLEAR
COLUMN bytes CLEAR
COLUMN size_mb CLEAR
COLUMN pct_of_pool CLEAR
COLUMN sp_size_mb CLEAR
COLUMN size_factor CLEAR
COLUMN estd_lc_mb CLEAR
COLUMN estd_lc_objects CLEAR
COLUMN estd_lc_time_saved CLEAR
COLUMN estd_time_factor CLEAR
COLUMN namespace CLEAR
COLUMN gets CLEAR
COLUMN gethits CLEAR
COLUMN get_hit_pct CLEAR
COLUMN pins CLEAR
COLUMN pinhits CLEAR
COLUMN pin_hit_pct CLEAR
COLUMN reloads CLEAR
COLUMN invalidations CLEAR
COLUMN reload_pct CLEAR
COLUMN sql_id CLEAR
COLUMN parsing_schema CLEAR
COLUMN sharable_mb CLEAR
COLUMN version_count CLEAR
COLUMN executions CLEAR
COLUMN loads CLEAR
COLUMN sql_text CLEAR

SET FEEDBACK ON
SET VERIFY ON
