/*******************************************************************************
*
* Script Name: memory.sql
* Title: Memory allocations
* Tags: Memory, SGA, PGA, Shared Pool
* Purpose: Show Oracle and OS memory configuration, allocations, usage, and sizing advice
*
* Description:
*   Provides an instance-level memory snapshot for the current connection.
*   It identifies the memory management mode, reports configured memory
*   targets and limits, summarizes SGA and PGA usage, breaks down SGA
*   allocations by pool/component,
*   highlights shared pool allocations, lists dynamic memory components,
*   shows the largest process PGA consumers, reports AMM sizing advice, and
*   summarizes host memory statistics.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$PARAMETER
*   - SELECT on V$SGA
*   - SELECT on V$SGAINFO
*   - SELECT on V$SGASTAT
*   - SELECT on V$PGASTAT
*   - SELECT on V$PROCESS
*   - SELECT on V$SESSION
*   - SELECT on V$MEMORY_DYNAMIC_COMPONENTS
*   - SELECT on V$MEMORY_TARGET_ADVICE
*   - SELECT on V$OSSTAT
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Memory management mode and configured memory parameters
*   - SGA summary from V$SGA and V$SGAINFO
*   - PGA summary from V$PGASTAT and V$PROCESS
*   - SGA allocations by pool/component from V$SGASTAT
*   - Shared pool allocation detail
*   - Dynamic memory components and recent resize state
*   - Top process PGA consumers
*   - MEMORY_TARGET advice when AMM is enabled
*   - Host CPU, physical memory, free memory, and paging statistics
*
* Example Usage:
*   SQL> @memory.sql
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

COLUMN memory_mode          FORMAT A28               HEADING 'Memory Mode'
COLUMN memory_target_gb     FORMAT 999,990.00        HEADING 'Mem Target GB'
COLUMN sga_target_gb        FORMAT 999,990.00        HEADING 'SGA Target GB'
COLUMN pga_target_gb        FORMAT 999,990.00        HEADING 'PGA Target GB'
COLUMN parameter            FORMAT A36               HEADING 'Parameter'
COLUMN display_value        FORMAT A40               HEADING 'Value'
COLUMN sga_name             FORMAT A36               HEADING 'SGA Component'
COLUMN sga_mb               FORMAT 999,999,990.00    HEADING 'MB'
COLUMN sga_gb               FORMAT 999,990.00        HEADING 'GB'
COLUMN info_name            FORMAT A36               HEADING 'SGA Info'
COLUMN info_mb              FORMAT 999,999,990.00    HEADING 'MB'
COLUMN resizeable           FORMAT A10               HEADING 'Resizeable'
COLUMN pga_stat             FORMAT A44               HEADING 'PGA Stat'
COLUMN pga_value            FORMAT A32               HEADING 'Value'
COLUMN process_count        FORMAT 999,999           HEADING 'Processes'
COLUMN pga_used_mb          FORMAT 999,999,990.00    HEADING 'PGA Used MB'
COLUMN pga_alloc_mb         FORMAT 999,999,990.00    HEADING 'PGA Alloc MB'
COLUMN pga_freeable_mb      FORMAT 999,999,990.00    HEADING 'PGA Freeable MB'
COLUMN pga_max_mb           FORMAT 999,999,990.00    HEADING 'PGA Max MB'
COLUMN pool                 FORMAT A18               HEADING 'Pool'
COLUMN allocation_name      FORMAT A44 TRUNC         HEADING 'Allocation'
COLUMN alloc_mb             FORMAT 999,999,990.00    HEADING 'MB'
COLUMN pct_of_sga_stat      FORMAT 990.00            HEADING 'Pct'
COLUMN shared_pool_name     FORMAT A48 TRUNC         HEADING 'Shared Pool Allocation'
COLUMN bytes                FORMAT 999,999,999,990   HEADING 'Bytes'
COLUMN pct_of_pool          FORMAT 990.00            HEADING 'Pct'
COLUMN component            FORMAT A36               HEADING 'Component'
COLUMN current_mb           FORMAT 999,999,990.00    HEADING 'Current MB'
COLUMN min_mb               FORMAT 999,999,990.00    HEADING 'Min MB'
COLUMN max_mb               FORMAT 999,999,990.00    HEADING 'Max MB'
COLUMN user_mb              FORMAT 999,999,990.00    HEADING 'User Spec MB'
COLUMN oper_count           FORMAT 999,999           HEADING 'Opers'
COLUMN last_oper_type       FORMAT A14               HEADING 'Last Oper'
COLUMN last_oper_mode       FORMAT A10               HEADING 'Mode'
COLUMN last_oper_time       FORMAT A19               HEADING 'Last Oper Time'
COLUMN granule_mb           FORMAT 999,990.00        HEADING 'Granule MB'
COLUMN sid                  FORMAT 99999             HEADING 'SID'
COLUMN serial#              FORMAT 99999999          HEADING 'Serial#'
COLUMN spid                 FORMAT A12               HEADING 'OS PID'
COLUMN username             FORMAT A24               HEADING 'Username'
COLUMN program              FORMAT A30 TRUNC         HEADING 'Program'
COLUMN pname                FORMAT A16               HEADING 'Process'
COLUMN status               FORMAT A8                HEADING 'Status'
COLUMN mem_target_gb        FORMAT 999,990.00        HEADING 'Target GB'
COLUMN target_factor        FORMAT 990.00            HEADING 'Factor'
COLUMN estd_db_time         FORMAT 999,999,999,990   HEADING 'Estd DB Time'
COLUMN estd_db_time_factor  FORMAT 990.00            HEADING 'Time Factor'
COLUMN version              FORMAT 999               HEADING 'Ver'
COLUMN stat_name            FORMAT A32               HEADING 'OS Stat'
COLUMN os_value             FORMAT 999,999,999,990.00 HEADING 'Value'
COLUMN os_unit              FORMAT A8                HEADING 'Unit'

PROMPT
PROMPT === Memory management mode ===
PROMPT

SELECT
    CASE
        WHEN NVL(MAX(CASE WHEN name = 'memory_target' THEN TO_NUMBER(value) END), 0) > 0
            THEN 'AMM (MEMORY_TARGET)'
        WHEN NVL(MAX(CASE WHEN name = 'sga_target' THEN TO_NUMBER(value) END), 0) > 0
            THEN 'ASMM (SGA_TARGET)'
        ELSE 'Manual'
    END AS memory_mode,
    ROUND(NVL(MAX(CASE WHEN name = 'memory_target' THEN TO_NUMBER(value) END), 0)
        / 1024 / 1024 / 1024, 2) AS memory_target_gb,
    ROUND(NVL(MAX(CASE WHEN name = 'sga_target' THEN TO_NUMBER(value) END), 0)
        / 1024 / 1024 / 1024, 2) AS sga_target_gb,
    ROUND(NVL(MAX(CASE WHEN name = 'pga_aggregate_target' THEN TO_NUMBER(value) END), 0)
        / 1024 / 1024 / 1024, 2) AS pga_target_gb
FROM v$parameter
WHERE name IN ('memory_target', 'sga_target', 'pga_aggregate_target');

PROMPT
PROMPT === Memory parameters ===
PROMPT

SELECT
    name AS parameter,
    NVL(display_value, '(not set)') AS display_value
FROM v$parameter
WHERE name IN (
    'memory_target',
    'memory_max_target',
    'sga_target',
    'sga_max_size',
    'pga_aggregate_target',
    'pga_aggregate_limit',
    'lock_sga',
    'pre_page_sga',
    'shared_pool_size',
    'shared_pool_reserved_size',
    'db_cache_size',
    'large_pool_size',
    'java_pool_size',
    'streams_pool_size',
    'inmemory_size',
    'result_cache_max_size',
    'log_buffer'
)
ORDER BY name;

PROMPT
PROMPT === SGA summary ===
PROMPT

SELECT
    name AS sga_name,
    ROUND(value / 1024 / 1024, 2) AS sga_mb,
    ROUND(value / 1024 / 1024 / 1024, 2) AS sga_gb
FROM v$sga
ORDER BY value DESC, name;

PROMPT
PROMPT === SGA information ===
PROMPT

SELECT
    name AS info_name,
    ROUND(bytes / 1024 / 1024, 2) AS info_mb,
    resizeable
FROM v$sgainfo
ORDER BY bytes DESC, name;

PROMPT
PROMPT === PGA summary ===
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
WHERE name IN (
    'aggregate PGA target parameter',
    'aggregate PGA auto target',
    'global memory bound',
    'total PGA inuse',
    'total PGA allocated',
    'maximum PGA allocated',
    'total freeable PGA memory',
    'process count',
    'over allocation count',
    'cache hit percentage'
)
ORDER BY name;

SELECT
    COUNT(*) AS process_count,
    ROUND(SUM(pga_used_mem) / 1024 / 1024, 2) AS pga_used_mb,
    ROUND(SUM(pga_alloc_mem) / 1024 / 1024, 2) AS pga_alloc_mb,
    ROUND(SUM(pga_freeable_mem) / 1024 / 1024, 2) AS pga_freeable_mb,
    ROUND(SUM(pga_max_mem) / 1024 / 1024, 2) AS pga_max_mb
FROM v$process;

PROMPT
PROMPT === SGA allocations by pool/component ===
PROMPT

SELECT
    NVL(pool, '(fixed)') AS pool,
    name AS allocation_name,
    ROUND(bytes / 1024 / 1024, 2) AS alloc_mb,
    ROUND(bytes / NULLIF(SUM(bytes) OVER (), 0) * 100, 2) AS pct_of_sga_stat
FROM (
    SELECT
        pool,
        name,
        SUM(bytes) AS bytes
    FROM v$sgastat
    GROUP BY pool, name
)
ORDER BY bytes DESC, pool, name;

PROMPT
PROMPT === Shared pool allocations ===
PROMPT

SELECT
    name AS shared_pool_name,
    bytes,
    ROUND(bytes / 1024 / 1024, 2) AS alloc_mb,
    ROUND(bytes / NULLIF(SUM(bytes) OVER (), 0) * 100, 2) AS pct_of_pool
FROM v$sgastat
WHERE pool = 'shared pool'
ORDER BY
    CASE WHEN name = 'free memory' THEN 0 ELSE 1 END,
    bytes DESC,
    name;

PROMPT
PROMPT === Dynamic memory components ===
PROMPT

SELECT
    component,
    ROUND(current_size / 1024 / 1024, 2) AS current_mb,
    ROUND(min_size / 1024 / 1024, 2) AS min_mb,
    ROUND(max_size / 1024 / 1024, 2) AS max_mb,
    ROUND(user_specified_size / 1024 / 1024, 2) AS user_mb,
    oper_count,
    last_oper_type,
    last_oper_mode,
    TO_CHAR(last_oper_time, 'YYYY-MM-DD HH24:MI:SS') AS last_oper_time,
    ROUND(granule_size / 1024 / 1024, 2) AS granule_mb
FROM v$memory_dynamic_components
WHERE current_size > 0
   OR user_specified_size > 0
ORDER BY current_size DESC, component;

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
        SUBSTR(NVL(s.program, p.program), 1, 30) AS program,
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
WHERE ROWNUM <= 20;

PROMPT
PROMPT === MEMORY_TARGET advice (AMM) ===
PROMPT

SELECT
    ROUND(memory_size / 1024, 2) AS mem_target_gb,
    memory_size_factor AS target_factor,
    estd_db_time,
    estd_db_time_factor,
    version
FROM v$memory_target_advice
ORDER BY memory_size;

PROMPT
PROMPT === OS memory ===
PROMPT

SELECT
    stat_name,
    CASE
        WHEN stat_name LIKE '%BYTES%'
          OR stat_name LIKE '%MEMORY%'
        THEN ROUND(value / 1024 / 1024 / 1024, 2)
        ELSE value
    END AS os_value,
    CASE
        WHEN stat_name LIKE '%BYTES%'
          OR stat_name LIKE '%MEMORY%'
        THEN 'GB'
        ELSE NULL
    END AS os_unit
FROM v$osstat
WHERE stat_name IN (
    'NUM_CPUS',
    'NUM_CPU_CORES',
    'PHYSICAL_MEMORY_BYTES',
    'FREE_MEMORY_BYTES',
    'AVAILABLE_FREE_MEMORY',
    'VM_IN_BYTES',
    'VM_OUT_BYTES'
)
ORDER BY stat_name;

COLUMN memory_mode CLEAR
COLUMN memory_target_gb CLEAR
COLUMN sga_target_gb CLEAR
COLUMN pga_target_gb CLEAR
COLUMN parameter CLEAR
COLUMN display_value CLEAR
COLUMN sga_name CLEAR
COLUMN sga_mb CLEAR
COLUMN sga_gb CLEAR
COLUMN info_name CLEAR
COLUMN info_mb CLEAR
COLUMN resizeable CLEAR
COLUMN pga_stat CLEAR
COLUMN pga_value CLEAR
COLUMN process_count CLEAR
COLUMN pga_used_mb CLEAR
COLUMN pga_alloc_mb CLEAR
COLUMN pga_freeable_mb CLEAR
COLUMN pga_max_mb CLEAR
COLUMN pool CLEAR
COLUMN allocation_name CLEAR
COLUMN alloc_mb CLEAR
COLUMN pct_of_sga_stat CLEAR
COLUMN shared_pool_name CLEAR
COLUMN bytes CLEAR
COLUMN pct_of_pool CLEAR
COLUMN component CLEAR
COLUMN current_mb CLEAR
COLUMN min_mb CLEAR
COLUMN max_mb CLEAR
COLUMN user_mb CLEAR
COLUMN oper_count CLEAR
COLUMN last_oper_type CLEAR
COLUMN last_oper_mode CLEAR
COLUMN last_oper_time CLEAR
COLUMN granule_mb CLEAR
COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN spid CLEAR
COLUMN username CLEAR
COLUMN program CLEAR
COLUMN pname CLEAR
COLUMN status CLEAR
COLUMN mem_target_gb CLEAR
COLUMN target_factor CLEAR
COLUMN estd_db_time CLEAR
COLUMN estd_db_time_factor CLEAR
COLUMN version CLEAR
COLUMN stat_name CLEAR
COLUMN os_value CLEAR
COLUMN os_unit CLEAR

SET FEEDBACK ON
SET VERIFY ON
