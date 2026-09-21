/*******************************************************************************
*
* Script Name: memory_usage.sql
* Title: Instance memory usage
* Tags: Memory, SGA, PGA
* Purpose: Show AMM vs ASMM vs manual memory settings, SGA/PGA sizes, dynamic components, and OS memory
*
* Description:
*   Classifies the instance as AMM (MEMORY_TARGET > 0), ASMM (SGA_TARGET > 0
*   with MEMORY_TARGET = 0), or Manual (both zero). Lists the memory
*   parameters, SGA breakdown from V$SGA, key PGA totals from V$PGASTAT,
*   and current sizes from V$MEMORY_DYNAMIC_COMPONENTS. V$MEMORY_TARGET_ADVICE
*   is populated when AMM is on. OS figures come from V$OSSTAT and vary by
*   platform. This is an instance-level snapshot of the session you are
*   connected to.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$PARAMETER
*   - SELECT on V$SGA
*   - SELECT on V$PGASTAT
*   - SELECT on V$MEMORY_DYNAMIC_COMPONENTS
*   - SELECT on V$MEMORY_TARGET_ADVICE
*   - SELECT on V$OSSTAT
*   - SELECT on V$PROCESS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Memory management mode (AMM, ASMM, or Manual)
*   - MEMORY_TARGET, SGA_TARGET, PGA_AGGREGATE_TARGET, and related parameters
*   - SGA component sizes
*   - PGA in-use, allocated, target, and process count
*   - Dynamic memory components and last resize
*   - MEMORY_TARGET advice (when AMM is enabled)
*   - OS CPU and physical memory
*
* Example Usage:
*   SQL> @memory_usage.sql
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
COLUMN sga_name             FORMAT A32               HEADING 'SGA Component'
COLUMN sga_mb               FORMAT 999,999,990.00    HEADING 'MB'
COLUMN sga_gb               FORMAT 999,990.00        HEADING 'GB'
COLUMN pga_stat             FORMAT A40               HEADING 'PGA Stat'
COLUMN pga_value            FORMAT A28               HEADING 'Value'
COLUMN component            FORMAT A36               HEADING 'Component'
COLUMN current_mb           FORMAT 999,999,990.00    HEADING 'Current MB'
COLUMN min_mb               FORMAT 999,999,990.00    HEADING 'Min MB'
COLUMN max_mb               FORMAT 999,999,990.00    HEADING 'Max MB'
COLUMN user_mb              FORMAT 999,999,990.00    HEADING 'User Spec MB'
COLUMN oper_count           FORMAT 999,999           HEADING 'Opers'
COLUMN last_oper_type       FORMAT A12               HEADING 'Last Oper'
COLUMN last_oper_mode       FORMAT A10               HEADING 'Mode'
COLUMN last_oper_time       FORMAT A19               HEADING 'Last Oper Time'
COLUMN granule_mb           FORMAT 999,990.00        HEADING 'Granule MB'
COLUMN mem_target_gb        FORMAT 999,990.00        HEADING 'Target GB'
COLUMN target_factor        FORMAT 990.00            HEADING 'Factor'
COLUMN estd_db_time         FORMAT 999,999,999,990   HEADING 'Estd DB Time'
COLUMN estd_db_time_factor  FORMAT 990.00            HEADING 'Time Factor'
COLUMN estd_phys_reads      FORMAT 999,999,999,990   HEADING 'Estd Phys Reads'
COLUMN version              FORMAT 999               HEADING 'Ver'
COLUMN stat_name            FORMAT A32               HEADING 'OS Stat'
COLUMN os_value             FORMAT 999,999,999,990.00 HEADING 'Value'
COLUMN os_unit              FORMAT A8                HEADING 'Unit'
COLUMN process_count        FORMAT 999,999           HEADING 'Processes'
COLUMN pga_used_mb          FORMAT 999,999,990.00    HEADING 'PGA Used MB'
COLUMN pga_alloc_mb         FORMAT 999,999,990.00    HEADING 'PGA Alloc MB'
COLUMN pga_max_mb           FORMAT 999,999,990.00    HEADING 'PGA Max MB'

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
    'db_cache_size',
    'large_pool_size',
    'java_pool_size',
    'streams_pool_size',
    'inmemory_size'
)
ORDER BY name;

PROMPT
PROMPT === SGA (V$SGA) ===
PROMPT

SELECT
    name AS sga_name,
    ROUND(value / 1024 / 1024, 2) AS sga_mb,
    ROUND(value / 1024 / 1024 / 1024, 2) AS sga_gb
FROM v$sga
ORDER BY value DESC, name;

PROMPT
PROMPT === PGA totals ===
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
    ROUND(SUM(pga_max_mem) / 1024 / 1024, 2) AS pga_max_mb
FROM v$process;

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
COLUMN pga_stat CLEAR
COLUMN pga_value CLEAR
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
COLUMN mem_target_gb CLEAR
COLUMN target_factor CLEAR
COLUMN estd_db_time CLEAR
COLUMN estd_db_time_factor CLEAR
COLUMN estd_phys_reads CLEAR
COLUMN version CLEAR
COLUMN stat_name CLEAR
COLUMN os_value CLEAR
COLUMN os_unit CLEAR
COLUMN process_count CLEAR
COLUMN pga_used_mb CLEAR
COLUMN pga_alloc_mb CLEAR
COLUMN pga_max_mb CLEAR

SET FEEDBACK ON
SET VERIFY ON
