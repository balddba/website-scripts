/*******************************************************************************
*
* Script Name: tde_report.sql
* Title: Transparent Data Encryption (TDE) report
* Tags: Security, Encryption, TDE, Storage
* Purpose: Report on Oracle TDE keystore/wallet status, master keys, encrypted tablespaces, tables, and columns
*
* Description:
*   Generates a comprehensive diagnostic report on Oracle Transparent Data
*   Encryption (TDE). The report inspects:
*   1. High-level TDE inventory and object count summary
*   2. Database initialization parameters for TDE and keystores
*   3. Keystore / Wallet configuration and open status across RAC instances (GV$ENCRYPTION_WALLET)
*   4. Master encryption keys and activation timestamps (V$ENCRYPTION_KEYS)
*   5. Tablespace encryption status, algorithms, and allocated sizes (DBA_TABLESPACES, V$ENCRYPTED_TABLESPACES)
*   6. User tables residing in encrypted tablespaces (summary by owner and detailed inventory)
*   7. Column-level encryption settings, algorithms, salt, and integrity MACs (DBA_ENCRYPTED_COLUMNS)
*   8. Encrypted SecureFile LOB segments (DBA_LOBS)
*
* Parameters:
*   &1 - (Optional) Schema owner filter for tables and columns (default: % for all schemas)
*
* Required Privileges:
*   - SELECT on GV$ENCRYPTION_WALLET (or V$ENCRYPTION_WALLET)
*   - SELECT on V$ENCRYPTION_KEYS
*   - SELECT on V$PARAMETER
*   - SELECT on DBA_TABLESPACES
*   - SELECT on V$TABLESPACE
*   - SELECT on V$ENCRYPTED_TABLESPACES
*   - SELECT on DBA_DATA_FILES and DBA_TEMP_FILES
*   - SELECT on DBA_TABLES and DBA_TAB_PARTITIONS
*   - SELECT on DBA_ENCRYPTED_COLUMNS
*   - SELECT on DBA_LOBS
*   - Or SELECT_CATALOG_ROLE / DBA
*
* Output Format:
*   - Overall TDE Summary (open wallets, encrypted TS count, tables, columns, LOBs)
*   - TDE Configuration Parameters (encrypt_new_tablespaces, wallet_root, tde_configuration)
*   - Keystore / Wallet Status (Instance, WRL Type, Keystore Location, Status, Wallet Type)
*   - Master Encryption Keys (Key ID Prefix, Key Use, Keystore Type, Creation, Activation, Tag)
*   - Tablespace Encryption Status (Tablespace, Type, Status, Encrypted, Algorithm, Size GB)
*   - Tables in Encrypted Tablespaces Summary (Owner, Tablespace, Table Count, Segments)
*   - Tables in Encrypted Tablespaces Detail (Owner, Table, Tablespace, Partitioned, Rows)
*   - Column-Level Encryption (Owner, Table, Column, Algorithm, Salt, Integrity Alg)
*   - Encrypted LOB Segments (Owner, Table, Column, Tablespace, SecureFile, Encrypt)
*
* Example Usage:
*   SQL> @tde_report.sql
*   SQL> @tde_report.sql HR
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 200
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN c_owner NEW_VALUE p_owner NOPRINT
SELECT UPPER(NVL(NULLIF(TRIM('&1'), ''), '%')) AS c_owner FROM dual;

COLUMN parameter             FORMAT A30             HEADING 'Parameter'
COLUMN value                 FORMAT A45             HEADING 'Value'
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
COLUMN key_id_short          FORMAT A30             HEADING 'Key ID (Prefix)'
COLUMN key_use               FORMAT A24             HEADING 'Key Use'
COLUMN keystore_type         FORMAT A14             HEADING 'Keystore Type'
COLUMN creation_time         FORMAT A19             HEADING 'Creation Time'
COLUMN activation_time       FORMAT A19             HEADING 'Activation Time'
COLUMN tag                   FORMAT A18             HEADING 'Tag'
COLUMN tablespace_name       FORMAT A22             HEADING 'Tablespace'
COLUMN ts_type               FORMAT A10             HEADING 'Type'
COLUMN ts_status             FORMAT A9              HEADING 'Status'
COLUMN encrypted             FORMAT A9              HEADING 'Encrypted'
COLUMN encryption_alg        FORMAT A14             HEADING 'Algorithm'
COLUMN tde_status            FORMAT A12             HEADING 'TDE Status'
COLUMN size_gb               FORMAT 999,990.00      HEADING 'Size GB'
COLUMN owner                 FORMAT A18             HEADING 'Owner'
COLUMN table_name            FORMAT A24             HEADING 'Table Name'
COLUMN table_count           FORMAT 999,990         HEADING 'Tables'
COLUMN segment_count         FORMAT 999,990         HEADING 'Segments'
COLUMN partitioned           FORMAT A11             HEADING 'Partitioned'
COLUMN num_rows              FORMAT 999,999,990     HEADING 'Num Rows'
COLUMN column_name           FORMAT A22             HEADING 'Column Name'
COLUMN salt                  FORMAT A6              HEADING 'Salt'
COLUMN integrity_alg         FORMAT A14             HEADING 'Integrity Alg'
COLUMN securefile            FORMAT A10             HEADING 'SecureFile'
COLUMN encrypt               FORMAT A8              HEADING 'Encrypt'
COLUMN open_wallets          FORMAT 999,990         HEADING 'Open Wallets'
COLUMN encrypted_ts_count    FORMAT 999,990         HEADING 'Encrypted TS'
COLUMN total_ts_count        FORMAT 999,990         HEADING 'Total TS'
COLUMN tables_in_encrypted_ts FORMAT 999,990        HEADING 'Encrypted Tables'
COLUMN encrypted_columns_count FORMAT 999,990       HEADING 'Encrypted Cols'
COLUMN encrypted_lobs_count  FORMAT 999,990         HEADING 'Encrypted LOBs'

PROMPT
PROMPT ===============================================================================
PROMPT Oracle Transparent Data Encryption (TDE) Report
PROMPT Filter Schema: &&p_owner
PROMPT ===============================================================================

PROMPT
PROMPT === 1. Overall TDE Summary ===
PROMPT

SELECT
    (SELECT COUNT(*) FROM gv$encryption_wallet WHERE status = 'OPEN') AS open_wallets,
    (SELECT COUNT(*) FROM dba_tablespaces WHERE encrypted = 'YES') AS encrypted_ts_count,
    (SELECT COUNT(*) FROM dba_tablespaces) AS total_ts_count,
    (SELECT COUNT(DISTINCT owner || '.' || table_name) FROM (
        SELECT t.owner, t.table_name FROM dba_tables t JOIN dba_tablespaces ts ON t.tablespace_name = ts.tablespace_name WHERE ts.encrypted = 'YES'
        UNION
        SELECT p.table_owner, p.table_name FROM dba_tab_partitions p JOIN dba_tablespaces ts ON p.tablespace_name = ts.tablespace_name WHERE ts.encrypted = 'YES'
    )) AS tables_in_encrypted_ts,
    (SELECT COUNT(*) FROM dba_encrypted_columns) AS encrypted_columns_count,
    (SELECT COUNT(*) FROM dba_lobs WHERE encrypt = 'YES') AS encrypted_lobs_count
FROM dual;

PROMPT
PROMPT === 2. TDE Configuration Parameters ===
PROMPT

SELECT
    name AS parameter,
    value
FROM v$parameter
WHERE name IN ('encrypt_new_tablespaces', 'wallet_root', 'tde_configuration')
ORDER BY name;

PROMPT
PROMPT === 3. Keystore / Wallet Status (GV$ENCRYPTION_WALLET) ===
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
PROMPT === 4. Master Encryption Keys (V$ENCRYPTION_KEYS) ===
PROMPT

SELECT
    NVL(k.activating_pdbname, NVL(k.creator_pdbname, NVL(c.name, 'CDB$ROOT'))) AS pdb_name,
    k.con_id,
    SUBSTR(k.key_id, 1, 30) AS key_id_short,
    k.key_use,
    k.keystore_type,
    TO_CHAR(k.creation_time, 'YYYY-MM-DD HH24:MI:SS') AS creation_time,
    TO_CHAR(k.activation_time, 'YYYY-MM-DD HH24:MI:SS') AS activation_time,
    k.tag
FROM v$encryption_keys k
LEFT JOIN v$containers c ON k.con_id = c.con_id
ORDER BY k.con_id, k.activation_time DESC NULLS LAST;

PROMPT
PROMPT === 5. Tablespace Encryption Status (DBA_TABLESPACES) ===
PROMPT

SELECT
    t.tablespace_name,
    t.contents AS ts_type,
    t.status AS ts_status,
    t.encrypted,
    NVL(e.encryptionalg, 'NONE') AS encryption_alg,
    NVL(e.status, 'UNENCRYPTED') AS tde_status,
    ROUND(NVL(SUM(f.bytes), 0) / 1024 / 1024 / 1024, 2) AS size_gb
FROM dba_tablespaces t
LEFT JOIN v$tablespace vt ON t.tablespace_name = vt.name
LEFT JOIN v$encrypted_tablespaces e ON vt.ts# = e.ts#
LEFT JOIN (
    SELECT tablespace_name, bytes FROM dba_data_files
    UNION ALL
    SELECT tablespace_name, bytes FROM dba_temp_files
) f ON t.tablespace_name = f.tablespace_name
GROUP BY
    t.tablespace_name,
    t.contents,
    t.status,
    t.encrypted,
    e.encryptionalg,
    e.status
ORDER BY
    CASE WHEN t.encrypted = 'YES' THEN 1 ELSE 2 END,
    t.tablespace_name;

PROMPT
PROMPT === 6. Tables in Encrypted Tablespaces (Summary by Owner) ===
PROMPT

SELECT
    obj.owner,
    obj.tablespace_name,
    COUNT(DISTINCT obj.table_name) AS table_count,
    COUNT(*) AS segment_count
FROM (
    SELECT t.owner, t.table_name, t.tablespace_name
    FROM dba_tables t
    JOIN dba_tablespaces ts ON t.tablespace_name = ts.tablespace_name
    WHERE ts.encrypted = 'YES'
      AND ( '&&p_owner' = '%' OR t.owner = '&&p_owner' )
    UNION ALL
    SELECT p.table_owner AS owner, p.table_name, p.tablespace_name
    FROM dba_tab_partitions p
    JOIN dba_tablespaces ts ON p.tablespace_name = ts.tablespace_name
    WHERE ts.encrypted = 'YES'
      AND ( '&&p_owner' = '%' OR p.table_owner = '&&p_owner' )
) obj
GROUP BY obj.owner, obj.tablespace_name
ORDER BY obj.owner, obj.tablespace_name;

PROMPT
PROMPT === 7. Tables in Encrypted Tablespaces (Detail) ===
PROMPT

SELECT
    t.owner,
    t.table_name,
    t.tablespace_name,
    t.partitioned,
    t.num_rows,
    NVL(e.encryptionalg, 'ENCRYPTED') AS encryption_alg
FROM dba_tables t
JOIN dba_tablespaces ts ON t.tablespace_name = ts.tablespace_name
LEFT JOIN v$tablespace vt ON ts.tablespace_name = vt.name
LEFT JOIN v$encrypted_tablespaces e ON vt.ts# = e.ts#
WHERE ts.encrypted = 'YES'
  AND ( '&&p_owner' = '%' OR t.owner = '&&p_owner' )
ORDER BY t.owner, t.table_name;

PROMPT
PROMPT === 8. Column-Level Encryption (DBA_ENCRYPTED_COLUMNS) ===
PROMPT

SELECT
    e.owner,
    e.table_name,
    e.column_name,
    e.encryption_alg,
    e.salt,
    e.integrity_alg
FROM dba_encrypted_columns e
WHERE ( '&&p_owner' = '%' OR e.owner = '&&p_owner' )
ORDER BY e.owner, e.table_name, e.column_name;

PROMPT
PROMPT === 9. Encrypted LOB Segments (DBA_LOBS) ===
PROMPT

SELECT
    l.owner,
    l.table_name,
    l.column_name,
    l.tablespace_name,
    l.securefile,
    l.encrypt
FROM dba_lobs l
WHERE l.encrypt = 'YES'
  AND ( '&&p_owner' = '%' OR l.owner = '&&p_owner' )
ORDER BY l.owner, l.table_name, l.column_name;

COLUMN parameter CLEAR
COLUMN value CLEAR
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
COLUMN key_id_short CLEAR
COLUMN key_use CLEAR
COLUMN keystore_type CLEAR
COLUMN creation_time CLEAR
COLUMN activation_time CLEAR
COLUMN tag CLEAR
COLUMN tablespace_name CLEAR
COLUMN ts_type CLEAR
COLUMN ts_status CLEAR
COLUMN encrypted CLEAR
COLUMN encryption_alg CLEAR
COLUMN tde_status CLEAR
COLUMN size_gb CLEAR
COLUMN owner CLEAR
COLUMN table_name CLEAR
COLUMN column_name CLEAR
COLUMN table_count CLEAR
COLUMN segment_count CLEAR
COLUMN partitioned CLEAR
COLUMN num_rows CLEAR
COLUMN salt CLEAR
COLUMN integrity_alg CLEAR
COLUMN securefile CLEAR
COLUMN encrypt CLEAR
COLUMN open_wallets CLEAR
COLUMN encrypted_ts_count CLEAR
COLUMN total_ts_count CLEAR
COLUMN tables_in_encrypted_ts CLEAR
COLUMN encrypted_columns_count CLEAR
COLUMN encrypted_lobs_count CLEAR

SET FEEDBACK ON
SET VERIFY ON
