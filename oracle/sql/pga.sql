/*******************************************************************************
*
* Script Name: pga.sql
* Title: PGA memory
* Tags: Memory, PGA
* Purpose: Report PGA target and limit, V$PGASTAT, target advice, and top process consumers
*
* Description:
*   Shows PGA_AGGREGATE_TARGET and PGA_AGGREGATE_LIMIT, every V$PGASTAT
*   row, V$PGA_TARGET_ADVICE, and the sessions with the largest PGA from
*   V$PROCESS joined to V$SESSION. Background processes are included;
*   they often hold more PGA than user sessions. Compare total allocated
*   PGA to the target and watch over-allocation count. PGA_AGGREGATE_LIMIT
*   of 0 means Oracle is using the default limit (12c and later).
*
* Parameters:
*   &1 - (Optional) Number of top PGA consumers to list. Default 20.
*        Press Enter at the SQL*Plus prompt if no argument is passed.
*
* Required Privileges:
*   - SELECT on V$PARAMETER
*   - SELECT on V$PGASTAT
*   - SELECT on V$PGA_TARGET_ADVICE
*   - SELECT on V$PROCESS
*   - SELECT on V$SESSION
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - PGA_AGGREGATE_TARGET and PGA_AGGREGATE_LIMIT
*   - All V$PGASTAT statistics
*   - Process-level used, allocated, and max PGA totals
*   - PGA_TARGET advice (estimated extra reads and cache hit)
*   - Top processes: SID, user, program, used/alloc/max PGA
*
* Example Usage:
*   SQL> @pga.sql
*   SQL> @pga.sql 30
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
COLUMN pga_stat             FORMAT A44               HEADING 'PGA Stat'
COLUMN pga_value            FORMAT A32               HEADING 'Value'
COLUMN process_count        FORMAT 999,999           HEADING 'Processes'
COLUMN pga_used_mb          FORMAT 999,999,990.00    HEADING 'Used MB'
COLUMN pga_alloc_mb         FORMAT 999,999,990.00    HEADING 'Alloc MB'
COLUMN pga_freeable_mb      FORMAT 999,999,990.00    HEADING 'Freeable MB'
COLUMN pga_max_mb           FORMAT 999,999,990.00    HEADING 'Max MB'
COLUMN pga_target_mb        FORMAT 999,999,990.00    HEADING 'Target MB'
COLUMN target_factor        FORMAT 990.00            HEADING 'Factor'
COLUMN advice_status        FORMAT A10               HEADING 'Status'
COLUMN bytes_processed_mb   FORMAT 999,999,999,990   HEADING 'Bytes Proc MB'
COLUMN estd_extra_mb        FORMAT 999,999,999,990   HEADING 'Estd Extra MB'
COLUMN estd_hit_pct         FORMAT 990.00            HEADING 'Estd Hit %'
COLUMN estd_overalloc       FORMAT 999,999,990       HEADING 'Estd Overalloc'
COLUMN sid                  FORMAT 99999             HEADING 'SID'
COLUMN serial#              FORMAT 99999999          HEADING 'Serial#'
COLUMN spid                 FORMAT A12               HEADING 'OS PID'
COLUMN username             FORMAT A24               HEADING 'Username'
COLUMN program              FORMAT A28 TRUNC         HEADING 'Program'
COLUMN pname                FORMAT A16               HEADING 'Process'
COLUMN status               FORMAT A8                HEADING 'Status'

PROMPT
PROMPT === PGA parameters ===
PROMPT

SELECT
    name AS parameter,
    NVL(display_value, '(not set)') AS display_value
FROM v$parameter
WHERE name IN (
    'pga_aggregate_target',
    'pga_aggregate_limit',
    'workarea_size_policy',
    'sort_area_size',
    'hash_area_size',
    'bitmap_merge_area_size'
)
ORDER BY name;

PROMPT
PROMPT === V$PGASTAT ===
PROMPT

SELECT
    name AS pga_stat,
    CASE
        WHEN unit = 'bytes'
        THEN TO_CHAR(ROUND(value / 1024 / 1024, 2), '999,999,990.00') || ' MB'
        WHEN unit = 'percent'
        THEN TO_CHAR(value, '990.00') || ' %'
        ELSE TO_CHAR(value, '999,999,999,990') || NVL2(unit, ' ' || unit, '')
    END AS pga_value
FROM v$pgastat
ORDER BY name;

PROMPT
PROMPT === Process PGA totals ===
PROMPT

SELECT
    COUNT(*) AS process_count,
    ROUND(SUM(pga_used_mem) / 1024 / 1024, 2) AS pga_used_mb,
    ROUND(SUM(pga_alloc_mem) / 1024 / 1024, 2) AS pga_alloc_mb,
    ROUND(SUM(pga_freeable_mem) / 1024 / 1024, 2) AS pga_freeable_mb,
    ROUND(SUM(pga_max_mem) / 1024 / 1024, 2) AS pga_max_mb
FROM v$process;

PROMPT
PROMPT === PGA_TARGET advice ===
PROMPT

SELECT
    ROUND(pga_target_for_estimate / 1024 / 1024, 2) AS pga_target_mb,
    pga_target_factor AS target_factor,
    advice_status,
    ROUND(bytes_processed / 1024 / 1024, 0) AS bytes_processed_mb,
    ROUND(estd_extra_bytes_rw / 1024 / 1024, 0) AS estd_extra_mb,
    estd_pga_cache_hit_percentage AS estd_hit_pct,
    estd_overalloc_count AS estd_overalloc
FROM v$pga_target_advice
ORDER BY pga_target_for_estimate;

PROMPT
PROMPT === Top PGA consumers ===
PROMPT

SELECT *
FROM (
    SELECT
        s.sid,
        s.serial#,
        p.spid,
        NVL(s.username, p.pname) AS username,
        p.pname,
        SUBSTR(NVL(s.program, p.program), 1, 28) AS program,
        s.status,
        ROUND(p.pga_used_mem / 1024 / 1024, 2) AS pga_used_mb,
        ROUND(p.pga_alloc_mem / 1024 / 1024, 2) AS pga_alloc_mb,
        ROUND(p.pga_freeable_mem / 1024 / 1024, 2) AS pga_freeable_mb,
        ROUND(p.pga_max_mem / 1024 / 1024, 2) AS pga_max_mb
    FROM v$process p
    LEFT JOIN v$session s
      ON s.paddr = p.addr
    ORDER BY p.pga_alloc_mem DESC NULLS LAST
)
WHERE ROWNUM <= TO_NUMBER('&&p_top');

COLUMN c_top CLEAR
COLUMN parameter CLEAR
COLUMN display_value CLEAR
COLUMN pga_stat CLEAR
COLUMN pga_value CLEAR
COLUMN process_count CLEAR
COLUMN pga_used_mb CLEAR
COLUMN pga_alloc_mb CLEAR
COLUMN pga_freeable_mb CLEAR
COLUMN pga_max_mb CLEAR
COLUMN pga_target_mb CLEAR
COLUMN target_factor CLEAR
COLUMN advice_status CLEAR
COLUMN bytes_processed_mb CLEAR
COLUMN estd_extra_mb CLEAR
COLUMN estd_hit_pct CLEAR
COLUMN estd_overalloc CLEAR
COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN spid CLEAR
COLUMN username CLEAR
COLUMN program CLEAR
COLUMN pname CLEAR
COLUMN status CLEAR

SET FEEDBACK ON
SET VERIFY ON
