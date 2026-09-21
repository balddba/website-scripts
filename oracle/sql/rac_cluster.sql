/*******************************************************************************
*
* Script Name: rac_cluster.sql
* Title: RAC cluster instances
* Tags: RAC, Cluster, Instance
* Purpose: Show instance membership, interconnects, and ASM clients for RAC or single-instance
*
* Description:
*   Lists every row in GV$INSTANCE (instance number, host, status, thread,
*   role) and V$ACTIVE_INSTANCES. On a single-instance database this is one
*   row; on RAC it is one row per instance. V$CLUSTER_INTERCONNECTS and
*   V$ASM_CLIENT are queried when present; they are empty on many
*   single-instance databases. Database role comes from V$DATABASE.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on GV$INSTANCE
*   - SELECT on V$DATABASE
*   - SELECT on V$PARAMETER
*   - SELECT on V$ACTIVE_INSTANCES
*   - SELECT on GV$CLUSTER_INTERCONNECTS
*   - SELECT on V$ASM_CLIENT
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Cluster_database parameter and database role
*   - Instances: number, name, host, status, thread, role
*   - Active instances
*   - Cluster interconnects
*   - ASM clients
*
* Example Usage:
*   SQL> @rac_cluster.sql
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

COLUMN metric            FORMAT A28              HEADING 'Metric'
COLUMN value             FORMAT A80              HEADING 'Value'
COLUMN inst_id           FORMAT 9990             HEADING 'Inst'
COLUMN instance_number   FORMAT 9990             HEADING 'Num'
COLUMN instance_name     FORMAT A16              HEADING 'Instance'
COLUMN host_name         FORMAT A32              HEADING 'Host'
COLUMN version           FORMAT A17              HEADING 'Version'
COLUMN status            FORMAT A12              HEADING 'Status'
COLUMN parallel          FORMAT A8               HEADING 'Parallel'
COLUMN thread#           FORMAT 9990             HEADING 'Thr'
COLUMN instance_role     FORMAT A18              HEADING 'Inst Role'
COLUMN database_role     FORMAT A18              HEADING 'DB Role'
COLUMN startup_time      FORMAT A19              HEADING 'Started'
COLUMN inst_number       FORMAT 9990             HEADING 'Num'
COLUMN inst_name         FORMAT A40              HEADING 'Active Instance'
COLUMN name              FORMAT A20              HEADING 'Name'
COLUMN ip_address        FORMAT A40              HEADING 'IP Address'
COLUMN is_public         FORMAT A8               HEADING 'Public'
COLUMN source            FORMAT A20              HEADING 'Source'
COLUMN group_number      FORMAT 9990             HEADING 'DG#'
COLUMN db_name           FORMAT A20              HEADING 'DB Name'
COLUMN software_version  FORMAT A20              HEADING 'Software'
COLUMN compatible_version FORMAT A20             HEADING 'Compatible'

PROMPT
PROMPT === Cluster identity ===
PROMPT

SELECT metric, value
FROM (
    SELECT 10 AS n, 'cluster_database' AS metric, value
    FROM v$parameter
    WHERE name = 'cluster_database'
    UNION ALL
    SELECT 20, 'cluster_database_instances', value
    FROM v$parameter
    WHERE name = 'cluster_database_instances'
    UNION ALL
    SELECT 30, 'instance_name', instance_name FROM v$instance
    UNION ALL
    SELECT 40, 'host_name', host_name FROM v$instance
    UNION ALL
    SELECT 50, 'db_unique_name', db_unique_name FROM v$database
    UNION ALL
    SELECT 60, 'database_role', database_role FROM v$database
    UNION ALL
    SELECT 70, 'open_mode', open_mode FROM v$database
)
ORDER BY n;

PROMPT
PROMPT === Instances (GV$INSTANCE) ===
PROMPT

SELECT
    i.inst_id,
    i.instance_number,
    i.instance_name,
    i.host_name,
    i.version,
    i.status,
    i.parallel,
    i.thread#,
    i.instance_role,
    d.database_role,
    TO_CHAR(i.startup_time, 'YYYY-MM-DD HH24:MI:SS') AS startup_time
FROM gv$instance i
CROSS JOIN v$database d
ORDER BY i.inst_id;

PROMPT
PROMPT === Active instances ===
PROMPT

SELECT inst_number, inst_name
FROM v$active_instances
ORDER BY inst_number;

PROMPT
PROMPT === Cluster interconnects ===
PROMPT
PROMPT Empty on most single-instance databases.

SELECT
    inst_id,
    name,
    ip_address,
    is_public,
    source
FROM gv$cluster_interconnects
ORDER BY inst_id, name, ip_address;

PROMPT
PROMPT === ASM clients ===
PROMPT
PROMPT Empty when this instance is not an ASM client.

SELECT
    group_number,
    instance_name,
    db_name,
    status,
    software_version,
    compatible_version
FROM v$asm_client
ORDER BY group_number, instance_name, db_name;

COLUMN metric CLEAR
COLUMN value CLEAR
COLUMN inst_id CLEAR
COLUMN instance_number CLEAR
COLUMN instance_name CLEAR
COLUMN host_name CLEAR
COLUMN version CLEAR
COLUMN status CLEAR
COLUMN parallel CLEAR
COLUMN thread# CLEAR
COLUMN instance_role CLEAR
COLUMN database_role CLEAR
COLUMN startup_time CLEAR
COLUMN inst_number CLEAR
COLUMN inst_name CLEAR
COLUMN name CLEAR
COLUMN ip_address CLEAR
COLUMN is_public CLEAR
COLUMN source CLEAR
COLUMN group_number CLEAR
COLUMN db_name CLEAR
COLUMN software_version CLEAR
COLUMN compatible_version CLEAR

SET FEEDBACK ON
SET VERIFY ON
