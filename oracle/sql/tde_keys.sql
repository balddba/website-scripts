/*******************************************************************************
*
* Script Name: tde_keys.sql
* Title: TDE encryption key information
* Tags: Security, Encryption, TDE, Keys, Multitenant, PDB
* Purpose: Report on Oracle TDE master encryption keys, keystore status, key history, and backup state across CDB and PDBs
*
* Description:
*   Generates a comprehensive diagnostic report on Oracle Transparent Data
*   Encryption (TDE) keys and keystores. In Multitenant (CDB/PDB) environments,
*   it reports key and wallet status for CDB$ROOT and all pluggable databases.
*   The report inspects:
*   1. Keystore / wallet configuration and open state across RAC instances and PDBs (GV$ENCRYPTION_WALLET)
*   2. Currently active master encryption key(s) per PDB with activation age and backup status
*   3. Full encryption key lifecycle history and rekey log per PDB (V$ENCRYPTION_KEYS)
*   4. Encrypted tablespace encryption key and algorithm mapping per container (V$ENCRYPTED_TABLESPACES)
*   5. Key management health and backup audit checks
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on GV$ENCRYPTION_WALLET (or V$ENCRYPTION_WALLET)
*   - SELECT on V$ENCRYPTION_KEYS
*   - SELECT on V$ENCRYPTED_TABLESPACES
*   - SELECT on V$TABLESPACE
*   - SELECT on V$CONTAINERS
*   - Or SELECT_CATALOG_ROLE / DBA
*
* Output Format:
*   - Keystore / Wallet Context (Instance, Con ID, Container Name, WRL Type, Location, Status, Wallet Type, Backed Up)
*   - Active Master Encryption Keys per PDB (Container Name, Con ID, Key ID, Key Use, Keystore Type, Activated Time, Age Days, Backed Up, Tag)
*   - Key Lifecycle & Rekey History (Container Name, Con ID, Key ID Prefix, State, Key Use, Created, Activated, Backed Up, Tag)
*   - Tablespace Encryption Key Mapping (Container Name, Tablespace, Algorithm, Key Status, Encrypted Key State)
*   - Key Security & Backup Health Checks (Check Name, Status, Details)
*
* Example Usage:
*   SQL> @tde_keys.sql
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

COLUMN inst_id               FORMAT 9990            HEADING 'Inst'
COLUMN con_id                FORMAT 9990            HEADING 'Con'
COLUMN container_name        FORMAT A20             HEADING 'Container / PDB'
COLUMN pdb_name              FORMAT A20             HEADING 'Container / PDB'
COLUMN wrl_type              FORMAT A10             HEADING 'WRL Type'
COLUMN wrl_parameter         FORMAT A44             HEADING 'Keystore Location / Parameter'
COLUMN status                FORMAT A15             HEADING 'Status'
COLUMN wallet_type           FORMAT A16             HEADING 'Wallet Type'
COLUMN wallet_order          FORMAT A10             HEADING 'Order'
COLUMN fully_backed_up       FORMAT A10             HEADING 'Backed Up'
COLUMN key_id                FORMAT A48             HEADING 'Key ID'
COLUMN key_id_prefix         FORMAT A30             HEADING 'Key ID Prefix'
COLUMN key_use               FORMAT A24             HEADING 'Key Use'
COLUMN keystore_type         FORMAT A14             HEADING 'Keystore Type'
COLUMN activated_time        FORMAT A19             HEADING 'Activated Time'
COLUMN created_time          FORMAT A19             HEADING 'Created Time'
COLUMN age_days              FORMAT 999,990.0       HEADING 'Age (Days)'
COLUMN backed_up             FORMAT A10             HEADING 'Backed Up'
COLUMN tag                   FORMAT A18             HEADING 'Tag'
COLUMN key_status            FORMAT A17             HEADING 'Key Status'
COLUMN tablespace_name       FORMAT A24             HEADING 'Tablespace'
COLUMN encryption_alg        FORMAT A14             HEADING 'Algorithm'
COLUMN encrypted_key_state   FORMAT A14             HEADING 'Key Present'
COLUMN check_name            FORMAT A28             HEADING 'Check Name'
COLUMN check_status          FORMAT A10             HEADING 'Status'
COLUMN details               FORMAT A60             HEADING 'Details'

PROMPT
PROMPT ===============================================================================
PROMPT Oracle TDE Encryption Key Information (CDB & PDBs)
PROMPT ===============================================================================

PROMPT
PROMPT === 1. Keystore / Wallet Context (GV$ENCRYPTION_WALLET) ===
PROMPT

SELECT
    w.inst_id,
    w.con_id,
    NVL(c.name, CASE WHEN w.con_id = 1 THEN 'CDB$ROOT' WHEN w.con_id = 0 THEN 'DATABASE' ELSE 'CON_ID ' || TO_CHAR(w.con_id) END) AS container_name,
    w.wrl_type,
    w.wrl_parameter,
    w.status,
    w.wallet_type,
    w.wallet_order,
    w.fully_backed_up
FROM gv$encryption_wallet w
LEFT JOIN v$containers c ON w.con_id = c.con_id
ORDER BY w.con_id, w.inst_id, w.wallet_order;

PROMPT
PROMPT === 2. Active Master Encryption Key(s) per Container / PDB ===
PROMPT

SELECT
    NVL(k.activating_pdbname, NVL(k.creator_pdbname, NVL(c.name, 'CDB$ROOT'))) AS pdb_name,
    k.con_id,
    k.key_id,
    k.key_use,
    k.keystore_type,
    TO_CHAR(k.activation_time, 'YYYY-MM-DD HH24:MI:SS') AS activated_time,
    ROUND(SYSDATE - CAST(k.activation_time AS DATE), 1) AS age_days,
    k.backed_up,
    NVL(k.tag, '(none)') AS tag
FROM (
    SELECT
        activating_pdbname,
        creator_pdbname,
        con_id,
        key_id,
        key_use,
        keystore_type,
        activation_time,
        backed_up,
        tag,
        ROW_NUMBER() OVER (
            PARTITION BY con_id, key_use
            ORDER BY activation_time DESC NULLS LAST
        ) AS rn
    FROM v$encryption_keys
    WHERE activation_time IS NOT NULL
) k
LEFT JOIN v$containers c ON k.con_id = c.con_id
WHERE k.rn = 1
ORDER BY k.con_id, k.key_use;

PROMPT
PROMPT === 3. Encryption Key History & Lifecycle per PDB (V$ENCRYPTION_KEYS) ===
PROMPT

SELECT
    NVL(k.activating_pdbname, NVL(k.creator_pdbname, NVL(c.name, 'CDB$ROOT'))) AS pdb_name,
    k.con_id,
    SUBSTR(k.key_id, 1, 30) AS key_id_prefix,
    CASE
        WHEN k.activation_time = MAX(k.activation_time) OVER (PARTITION BY k.con_id, k.key_use) THEN 'ACTIVE (CURRENT)'
        WHEN k.activation_time IS NOT NULL THEN 'RETIRED'
        ELSE 'PENDING'
    END AS key_status,
    k.key_use,
    k.keystore_type,
    TO_CHAR(k.creation_time, 'YYYY-MM-DD HH24:MI:SS') AS created_time,
    TO_CHAR(k.activation_time, 'YYYY-MM-DD HH24:MI:SS') AS activated_time,
    k.backed_up,
    k.tag
FROM v$encryption_keys k
LEFT JOIN v$containers c ON k.con_id = c.con_id
ORDER BY k.con_id, k.activation_time DESC NULLS LAST, k.creation_time DESC;

PROMPT
PROMPT === 4. Tablespace Encryption Keys & Algorithms ===
PROMPT

SELECT
    NVL(c.name, 'CDB$ROOT') AS pdb_name,
    vt.name AS tablespace_name,
    e.encryptionalg AS encryption_alg,
    e.status AS key_status,
    CASE
        WHEN e.encrypted_key IS NOT NULL THEN 'PRESENT'
        ELSE 'NONE'
    END AS encrypted_key_state
FROM v$encrypted_tablespaces e
JOIN v$tablespace vt ON e.ts# = vt.ts# AND e.con_id = vt.con_id
LEFT JOIN v$containers c ON e.con_id = c.con_id
ORDER BY e.con_id, vt.name;

PROMPT
PROMPT === 5. Key Security & Backup Health Checks ===
PROMPT

SELECT
    check_name,
    check_status,
    details
FROM (
    SELECT
        'Active Keystore Status' AS check_name,
        CASE
            WHEN COUNT(*) > 0 AND COUNT(CASE WHEN status <> 'OPEN' THEN 1 END) = 0 THEN 'OK'
            WHEN COUNT(*) = 0 THEN 'WARNING'
            ELSE 'CRITICAL'
        END AS check_status,
        CASE
            WHEN COUNT(*) = 0 THEN 'No keystore wallet found; TDE is not configured.'
            WHEN COUNT(CASE WHEN status <> 'OPEN' THEN 1 END) = 0 THEN 'All keystore instances and PDBs are OPEN.'
            ELSE 'One or more keystore instances/PDBs are NOT OPEN.'
        END AS details
    FROM gv$encryption_wallet
    UNION ALL
    SELECT
        'Master Key Backed Up' AS check_name,
        CASE
            WHEN COUNT(*) = 0 THEN 'INFO'
            WHEN COUNT(CASE WHEN backed_up <> 'YES' THEN 1 END) = 0 THEN 'OK'
            ELSE 'WARNING'
        END AS check_status,
        CASE
            WHEN COUNT(*) = 0 THEN 'No master keys recorded.'
            WHEN COUNT(CASE WHEN backed_up <> 'YES' THEN 1 END) = 0 THEN 'All master encryption keys (CDB & PDBs) are backed up in keystore.'
            ELSE TO_CHAR(COUNT(CASE WHEN backed_up <> 'YES' THEN 1 END)) || ' key(s) are NOT backed up! Backup keystore immediately.'
        END AS details
    FROM v$encryption_keys
    UNION ALL
    SELECT
        'Keystore Full Backup' AS check_name,
        CASE
            WHEN COUNT(*) = 0 THEN 'INFO'
            WHEN COUNT(CASE WHEN fully_backed_up = 'NO' THEN 1 END) = 0 THEN 'OK'
            ELSE 'WARNING'
        END AS check_status,
        CASE
            WHEN COUNT(*) = 0 THEN 'No keystore wallet found.'
            WHEN COUNT(CASE WHEN fully_backed_up = 'NO' THEN 1 END) = 0 THEN 'Keystore has been fully backed up.'
            ELSE 'Keystore has pending modifications not yet backed up.'
        END AS details
    FROM gv$encryption_wallet
)
ORDER BY check_name;

COLUMN inst_id CLEAR
COLUMN con_id CLEAR
COLUMN container_name CLEAR
COLUMN pdb_name CLEAR
COLUMN wrl_type CLEAR
COLUMN wrl_parameter CLEAR
COLUMN status CLEAR
COLUMN wallet_type CLEAR
COLUMN wallet_order CLEAR
COLUMN fully_backed_up CLEAR
COLUMN key_id CLEAR
COLUMN key_id_prefix CLEAR
COLUMN key_use CLEAR
COLUMN keystore_type CLEAR
COLUMN activated_time CLEAR
COLUMN created_time CLEAR
COLUMN age_days CLEAR
COLUMN backed_up CLEAR
COLUMN tag CLEAR
COLUMN key_status CLEAR
COLUMN tablespace_name CLEAR
COLUMN encryption_alg CLEAR
COLUMN encrypted_key_state CLEAR
COLUMN check_name CLEAR
COLUMN check_status CLEAR
COLUMN details CLEAR

SET FEEDBACK ON
SET VERIFY ON
