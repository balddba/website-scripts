/*******************************************************************************
*
* Script Name: pdbs.sql
* Title: Pluggable database status
* Tags: PDB, RAC, Multitenant
* Purpose: Show each PDB's open mode per instance, restricted flag, open time, and local undo
*
* Description:
*   Lists CDB$ROOT, PDB$SEED, and every pluggable database from GV$PDBS so a
*   RAC database shows open mode on each instance. Restricted, open time, and
*   local undo come from the instance view plus CDB_PDBS. Run it from CDB$ROOT
*   (12.2 or later) to see every PDB; a non-RAC database still returns one
*   row per PDB.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on GV$PDBS
*   - SELECT on GV$INSTANCE
*   - SELECT on CDB_PDBS
*   - SELECT on V$PARAMETER
*
* Output Format:
*   - Container id and PDB name
*   - Instance id and instance name
*   - Open mode, restricted flag, and open time
*   - Local undo (YES/NO)
*   - Dictionary status from CDB_PDBS
*
* Example Usage:
*   SQL> @pdbs.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET LINESIZE 180
SET PAGESIZE 100

COLUMN con_id         FORMAT 9990            HEADING 'Con ID'
COLUMN pdb_name       FORMAT A30             HEADING 'PDB Name'
COLUMN inst_id        FORMAT 9990            HEADING 'Inst'
COLUMN instance_name  FORMAT A16             HEADING 'Instance'
COLUMN open_mode      FORMAT A10             HEADING 'Open Mode'
COLUMN restricted     FORMAT A10             HEADING 'Restricted'
COLUMN open_time      FORMAT A19             HEADING 'Opened'
COLUMN local_undo     FORMAT A16             HEADING 'Local Undo'
COLUMN pdb_status     FORMAT A12             HEADING 'Status'

SELECT
    p.con_id,
    p.name AS pdb_name,
    p.inst_id,
    i.instance_name,
    p.open_mode,
    p.restricted,
    TO_CHAR(p.open_time, 'YYYY-MM-DD HH24:MI:SS') AS open_time,
    NVL(
        p.local_undo,
        CASE
            WHEN UPPER(prm.value) = 'TRUE' THEN 'YES'
            WHEN UPPER(prm.value) = 'FALSE' THEN 'NO'
        END
    ) AS local_undo,
    c.status AS pdb_status
FROM gv$pdbs p
JOIN gv$instance i
    ON i.inst_id = p.inst_id
LEFT JOIN cdb_pdbs c
    ON c.con_id = p.con_id
LEFT JOIN v$parameter prm
    ON prm.name = 'local_undo_enabled'
ORDER BY
    p.con_id,
    p.inst_id;
