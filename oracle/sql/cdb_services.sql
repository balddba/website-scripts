/*******************************************************************************
*
* Script Name: cdb_services.sql
* Title: CDB Service Mapping
* Tags: Multitenant, Services, RAC
* Purpose: Maps database services to their target PDBs and active RAC instances from cdb_services and gv$active_services.
*
* Description:
*   Maps all configured database services across CDB containers and pluggable
*   databases to their active RAC instances. Queries CDB_SERVICES for service
*   configuration (such as failover attributes, runtime load balancing goals,
*   and connection load balancing goals) and outer joins with GV$ACTIVE_SERVICES
*   to show which instances are actively hosting each service.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on CDB_SERVICES
*   - SELECT on GV$ACTIVE_SERVICES
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Con ID and PDB Name
*   - Service Name and Network Name
*   - Active Instance ID (Inst ID)
*   - Blocked Status
*   - Runtime Goal (GOAL) and Connection Load Balancing Goal (CLB_GOAL)
*   - Failover Method and Failover Type
*
* Example Usage:
*   sqlplus user/password@yourdb @cdb_services.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET LINESIZE 200
SET PAGESIZE 100
SET VERIFY OFF
SET FEEDBACK OFF

COLUMN con_id          FORMAT 9990            HEADING 'Con ID'
COLUMN pdb_name        FORMAT A20             HEADING 'PDB Name'
COLUMN service_name    FORMAT A30             HEADING 'Service Name'
COLUMN network_name    FORMAT A30             HEADING 'Network Name'
COLUMN inst_id         FORMAT 9990            HEADING 'Inst'
COLUMN blocked         FORMAT A8              HEADING 'Blocked'
COLUMN goal            FORMAT A12             HEADING 'Goal'
COLUMN clb_goal        FORMAT A10             HEADING 'CLB Goal'
COLUMN failover_method FORMAT A12             HEADING 'FO Method'
COLUMN failover_type   FORMAT A12             HEADING 'FO Type'

SELECT
    s.con_id,
    NVL(s.pdb, 'CDB$ROOT') AS pdb_name,
    s.name AS service_name,
    s.network_name,
    a.inst_id,
    a.blocked,
    s.goal,
    s.clb_goal,
    s.failover_method,
    s.failover_type
FROM cdb_services s
LEFT JOIN gv$active_services a
    ON a.name = s.name
    AND a.con_id = s.con_id
ORDER BY
    s.con_id,
    s.name,
    a.inst_id;

COLUMN con_id CLEAR
COLUMN pdb_name CLEAR
COLUMN service_name CLEAR
COLUMN network_name CLEAR
COLUMN inst_id CLEAR
COLUMN blocked CLEAR
COLUMN goal CLEAR
COLUMN clb_goal CLEAR
COLUMN failover_method CLEAR
COLUMN failover_type CLEAR

SET FEEDBACK ON
SET VERIFY ON
