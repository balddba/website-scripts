/*******************************************************************************
*
* Script Name: tables_without_pk.sql
* Title: Tables without a primary key
* Tags: Constraints, Tables
* Purpose: List tables that have no primary key constraint
*
* Description:
*   Reports heap and other application tables with no PRIMARY KEY in
*   DBA_CONSTRAINTS. Oracle-maintained schemas (DBA_USERS.ORACLE_MAINTAINED
*   = 'N' only), recycle-bin objects, nested tables, secondary tables, and
*   IOT overflow/mapping segments are omitted. Optional schema filter.
*
* Parameters:
*   &1 - (Optional) Schema owner. Default is % (every non-Oracle-maintained
*        schema). Press Enter at the SQL*Plus prompt if no argument is passed.
*
* Required Privileges:
*   - SELECT on DBA_TABLES
*   - SELECT on DBA_CONSTRAINTS
*   - SELECT on DBA_USERS
*
* Output Format:
*   - Owner, table name, NUM_ROWS, partitioned flag, and IOT_TYPE
*
* Example Usage:
*   SQL> @tables_without_pk.sql
*   SQL> @tables_without_pk.sql HR
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 160
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF
SET NULL '(null)'

-- Optional &1: SQL*Plus prompts if omitted; Enter (empty) means all user schemas.
COLUMN c_owner NEW_VALUE p_owner NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), '%') AS c_owner FROM dual;

VARIABLE tab_owner VARCHAR2(128)

BEGIN
    :tab_owner := UPPER(TRIM('&&p_owner'));

    IF :tab_owner <> '%'
       AND NOT REGEXP_LIKE(:tab_owner, '^[A-Z][A-Z0-9_$#]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Schema must be an ordinary Oracle identifier or %.'
        );
    END IF;
END;
/

COLUMN owner        FORMAT A30            HEADING 'Owner'
COLUMN table_name   FORMAT A40            HEADING 'Table Name'
COLUMN num_rows     FORMAT 999,999,999,990 HEADING 'Num Rows'
COLUMN partitioned  FORMAT A11            HEADING 'Partitioned'
COLUMN iot_type     FORMAT A12            HEADING 'IOT Type'

PROMPT
PROMPT === Tables without a primary key ===
PROMPT

SELECT
    t.owner,
    t.table_name,
    t.num_rows,
    t.partitioned,
    t.iot_type
FROM dba_tables t
JOIN dba_users u
  ON u.username = t.owner
WHERE u.oracle_maintained = 'N'
  AND (:tab_owner = '%' OR t.owner = :tab_owner)
  AND t.table_name NOT LIKE 'BIN$%'
  AND NVL(t.nested, 'NO') = 'NO'
  AND NVL(t.secondary, 'N') <> 'Y'
  AND NVL(t.iot_type, 'HEAP') NOT IN ('IOT_OVERFLOW', 'IOT_MAPPING')
  AND NOT EXISTS (
        SELECT 1
        FROM dba_constraints c
        WHERE c.owner = t.owner
          AND c.table_name = t.table_name
          AND c.constraint_type = 'P'
      )
ORDER BY t.owner, t.table_name;

COLUMN owner CLEAR
COLUMN table_name CLEAR
COLUMN num_rows CLEAR
COLUMN partitioned CLEAR
COLUMN iot_type CLEAR

UNDEFINE p_owner
UNDEFINE 1

SET FEEDBACK ON
SET VERIFY ON
SET NULL ''
