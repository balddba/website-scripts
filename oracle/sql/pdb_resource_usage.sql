/*******************************************************************************
*
* Script Name: pdb_resource_usage.sql
* Title: PDB Resource Usage
* Tags: Multitenant, PDB, Resource Manager, Performance
* Purpose: Monitors PDB CPU, memory, and I/O resource consumption metrics from gv$rsrcpdbmetric / v$rsrcpdbmetric.
*
* Description:
*   Displays real-time and recent Resource Manager metric snapshots for each
*   pluggable database across RAC instances using GV$RSRCPDBMETRIC. Reports
*   CPU utilization, active/waiting sessions, I/O rates (IOPS and MB/s),
*   and memory allocation (Buffer Cache, PGA, Shared Pool).
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on GV$RSRCPDBMETRIC (or V$RSRCPDBMETRIC)
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Instance ID and Container ID
*   - PDB Name
*   - Average CPU Utilization (%) and CPU Consumed Time (ms)
*   - Active and Waiting Session counts
*   - I/O Performance: IOPS and I/O Throughput (MB/s)
*   - Memory Usage: Buffer Cache MB, PGA MB, Shared Pool MB
*
* Example Usage:
*   sqlplus user/password@yourdb @pdb_resource_usage.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET LINESIZE 200
SET PAGESIZE 100
SET VERIFY OFF
SET FEEDBACK OFF

COLUMN inst_id          FORMAT 9990            HEADING 'Inst'
COLUMN con_id           FORMAT 9990            HEADING 'Con ID'
COLUMN pdb_name         FORMAT A25             HEADING 'PDB Name'
COLUMN avg_cpu_util     FORMAT 990.99          HEADING 'Avg CPU %'
COLUMN cpu_consumed_ms  FORMAT 999,999,990     HEADING 'CPU Cons (ms)'
COLUMN avg_running_sess FORMAT 990.99          HEADING 'Avg Run Sess'
COLUMN avg_waiting_sess FORMAT 990.99          HEADING 'Avg Wait Sess'
COLUMN iops             FORMAT 999,990.9       HEADING 'IOPS'
COLUMN iombps           FORMAT 999,990.99      HEADING 'I/O MB/s'
COLUMN buffer_cache_mb  FORMAT 999,990.0       HEADING 'Buffer MB'
COLUMN pga_mb           FORMAT 999,990.0       HEADING 'PGA MB'
COLUMN shared_pool_mb   FORMAT 999,990.0       HEADING 'Shared Pool MB'

SELECT
    inst_id,
    con_id,
    pdb_name,
    avg_cpu_utilization AS avg_cpu_util,
    cpu_consumed_time AS cpu_consumed_ms,
    avg_running_sessions AS avg_running_sess,
    avg_waiting_sessions AS avg_waiting_sess,
    iops,
    iombps,
    ROUND(buffer_cache_bytes / 1024 / 1024, 1) AS buffer_cache_mb,
    ROUND(pga_bytes / 1024 / 1024, 1) AS pga_mb,
    ROUND(shared_pool_bytes / 1024 / 1024, 1) AS shared_pool_mb
FROM gv$rsrcpdbmetric
ORDER BY
    inst_id,
    con_id;

COLUMN inst_id CLEAR
COLUMN con_id CLEAR
COLUMN pdb_name CLEAR
COLUMN avg_cpu_util CLEAR
COLUMN cpu_consumed_ms CLEAR
COLUMN avg_running_sess CLEAR
COLUMN avg_waiting_sess CLEAR
COLUMN iops CLEAR
COLUMN iombps CLEAR
COLUMN buffer_cache_mb CLEAR
COLUMN pga_mb CLEAR
COLUMN shared_pool_mb CLEAR

SET FEEDBACK ON
SET VERIFY ON
