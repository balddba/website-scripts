/*******************************************************************************
*
* Script Name: sga.sql
* Title: SGA memory
* Tags: Memory, SGA
* Purpose: Report SGA size, V$SGAINFO, dynamic components, recent resize operations, and SGA_TARGET
*
* Description:
*   Shows SGA_TARGET and SGA_MAX_SIZE, the V$SGA totals, V$SGAINFO
*   (including which areas are resizeable), current V$SGA_DYNAMIC_COMPONENTS
*   sizes, and recent V$SGA_RESIZE_OPS. Under AMM, MEMORY_TARGET drives
*   SGA_TARGET; under ASMM, SGA_TARGET is the pool of autotuned cache
*   memory. Manual pool sizes appear as user-specified values on the
*   dynamic components. Resize history is instance lifetime until aged
*   out; this script keeps the newest rows.
*
* Parameters:
*   &1 - (Optional) Number of recent resize operations to list. Default 30.
*        Press Enter at the SQL*Plus prompt if no argument is passed.
*
* Required Privileges:
*   - SELECT on V$PARAMETER
*   - SELECT on V$SGA
*   - SELECT on V$SGAINFO
*   - SELECT on V$SGA_DYNAMIC_COMPONENTS
*   - SELECT on V$SGA_RESIZE_OPS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - SGA_TARGET, SGA_MAX_SIZE, and MEMORY_TARGET
*   - V$SGA component sizes
*   - V$SGAINFO bytes and resizeable flag
*   - Dynamic component current/min/max and last operation
*   - Recent resize operations with initial, target, and final size
*
* Example Usage:
*   SQL> @sga.sql
*   SQL> @sga.sql 50
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

-- Optional &1: SQL*Plus prompts if omitted; Enter (empty) means 30 rows.
COLUMN c_rows NEW_VALUE p_rows NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), '30') AS c_rows FROM dual;

COLUMN parameter            FORMAT A36               HEADING 'Parameter'
COLUMN display_value        FORMAT A40               HEADING 'Value'
COLUMN sga_name             FORMAT A32               HEADING 'SGA Component'
COLUMN sga_mb               FORMAT 999,999,990.00    HEADING 'MB'
COLUMN sga_gb               FORMAT 999,990.00        HEADING 'GB'
COLUMN info_name            FORMAT A36               HEADING 'SGA Info'
COLUMN info_mb              FORMAT 999,999,990.00    HEADING 'MB'
COLUMN resizeable           FORMAT A10               HEADING 'Resizeable'
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
COLUMN oper_type            FORMAT A12               HEADING 'Oper'
COLUMN oper_mode            FORMAT A10               HEADING 'Mode'
COLUMN sga_parameter        FORMAT A28               HEADING 'Parameter'
COLUMN initial_mb           FORMAT 999,999,990.00    HEADING 'Initial MB'
COLUMN target_mb            FORMAT 999,999,990.00    HEADING 'Target MB'
COLUMN final_mb             FORMAT 999,999,990.00    HEADING 'Final MB'
COLUMN status               FORMAT A10               HEADING 'Status'
COLUMN start_time           FORMAT A19               HEADING 'Start'
COLUMN end_time             FORMAT A19               HEADING 'End'

PROMPT
PROMPT === SGA parameters ===
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
    'lock_sga',
    'pre_page_sga',
    'shared_pool_size',
    'db_cache_size',
    'large_pool_size',
    'java_pool_size',
    'streams_pool_size',
    'inmemory_size',
    'log_buffer'
)
ORDER BY name;

PROMPT
PROMPT === V$SGA ===
PROMPT

SELECT
    name AS sga_name,
    ROUND(value / 1024 / 1024, 2) AS sga_mb,
    ROUND(value / 1024 / 1024 / 1024, 2) AS sga_gb
FROM v$sga
ORDER BY value DESC, name;

PROMPT
PROMPT === V$SGAINFO ===
PROMPT

SELECT
    name AS info_name,
    ROUND(bytes / 1024 / 1024, 2) AS info_mb,
    resizeable
FROM v$sgainfo
ORDER BY bytes DESC, name;

PROMPT
PROMPT === Dynamic SGA components ===
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
FROM v$sga_dynamic_components
WHERE current_size > 0
   OR user_specified_size > 0
ORDER BY current_size DESC, component;

PROMPT
PROMPT === Recent SGA resize operations ===
PROMPT

SELECT *
FROM (
    SELECT
        component,
        oper_type,
        oper_mode,
        parameter AS sga_parameter,
        ROUND(initial_size / 1024 / 1024, 2) AS initial_mb,
        ROUND(target_size / 1024 / 1024, 2) AS target_mb,
        ROUND(final_size / 1024 / 1024, 2) AS final_mb,
        status,
        TO_CHAR(start_time, 'YYYY-MM-DD HH24:MI:SS') AS start_time,
        TO_CHAR(end_time, 'YYYY-MM-DD HH24:MI:SS') AS end_time
    FROM v$sga_resize_ops
    ORDER BY start_time DESC
)
WHERE ROWNUM <= TO_NUMBER('&&p_rows');

COLUMN c_rows CLEAR
COLUMN parameter CLEAR
COLUMN display_value CLEAR
COLUMN sga_name CLEAR
COLUMN sga_mb CLEAR
COLUMN sga_gb CLEAR
COLUMN info_name CLEAR
COLUMN info_mb CLEAR
COLUMN resizeable CLEAR
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
COLUMN oper_type CLEAR
COLUMN oper_mode CLEAR
COLUMN sga_parameter CLEAR
COLUMN initial_mb CLEAR
COLUMN target_mb CLEAR
COLUMN final_mb CLEAR
COLUMN status CLEAR
COLUMN start_time CLEAR
COLUMN end_time CLEAR

SET FEEDBACK ON
SET VERIFY ON
