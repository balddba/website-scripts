/*******************************************************************************
*
* Script Name: redundant_constraints.sql
* Title: Redundant constraints
* Tags: Constraints, Tuning
* Purpose: Find unique/PK, foreign-key, and check constraints that duplicate another on the same table
*
* Description:
*   Pairs constraints on the same table that encode the same rule: primary or
*   unique keys on the same column set (including PK plus unique overlap),
*   foreign keys on the same child columns, and check constraints whose
*   SEARCH_CONDITION_VC text matches after whitespace normalization.
*   Oracle-maintained schemas and recycle-bin tables are skipped. Check
*   comparison needs SEARCH_CONDITION_VC (12.2+). Display only.
*
* Parameters:
*   &1 - (Optional) Schema owner. Default is % (every non-Oracle-maintained
*        schema). Press Enter at the SQL*Plus prompt if no argument is passed.
*
* Required Privileges:
*   - SELECT on DBA_CONSTRAINTS
*   - SELECT on DBA_CONS_COLUMNS
*   - SELECT on DBA_USERS
*
* Output Format:
*   - Owner, table, both constraint names and types, status, column list or
*     check text, and a redundancy reason
*
* Example Usage:
*   SQL> @redundant_constraints.sql
*   SQL> @redundant_constraints.sql HR
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 280
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF
SET NULL '(null)'

-- Optional &1: SQL*Plus prompts if omitted; Enter (empty) means all user schemas.
COLUMN c_owner NEW_VALUE p_owner NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), '%') AS c_owner FROM dual;

VARIABLE cons_owner VARCHAR2(128)

BEGIN
    :cons_owner := UPPER(TRIM('&&p_owner'));

    IF :cons_owner <> '%'
       AND NOT REGEXP_LIKE(:cons_owner, '^[A-Z][A-Z0-9_$#]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Schema must be an ordinary Oracle identifier or %.'
        );
    END IF;
END;
/

COLUMN owner          FORMAT A20  HEADING 'Owner'
COLUMN table_name     FORMAT A30  HEADING 'Table'
COLUMN constraint_1   FORMAT A30  HEADING 'Constraint 1'
COLUMN type_1         FORMAT A6   HEADING 'Type 1'
COLUMN status_1       FORMAT A9   HEADING 'Status 1'
COLUMN constraint_2   FORMAT A30  HEADING 'Constraint 2'
COLUMN type_2         FORMAT A6   HEADING 'Type 2'
COLUMN status_2       FORMAT A9   HEADING 'Status 2'
COLUMN details        FORMAT A70  HEADING 'Columns / Check'
COLUMN redundancy     FORMAT A40  HEADING 'Redundancy'

PROMPT
PROMPT === Redundant unique, primary key, foreign key, and check constraints ===
PROMPT

WITH keyed AS (
    SELECT
        c.owner,
        c.table_name,
        c.constraint_name,
        c.constraint_type,
        c.status,
        c.r_owner,
        c.r_constraint_name,
        LISTAGG(cc.column_name, ', ') WITHIN GROUP (ORDER BY cc.column_name) AS col_list_set
    FROM dba_constraints c
    JOIN dba_cons_columns cc
      ON cc.owner = c.owner
     AND cc.constraint_name = c.constraint_name
     AND cc.table_name = c.table_name
    JOIN dba_users u
      ON u.username = c.owner
    WHERE c.constraint_type IN ('P', 'U', 'R')
      AND u.oracle_maintained = 'N'
      AND c.table_name NOT LIKE 'BIN$%'
      AND (:cons_owner = '%' OR c.owner = :cons_owner)
    GROUP BY
        c.owner,
        c.table_name,
        c.constraint_name,
        c.constraint_type,
        c.status,
        c.r_owner,
        c.r_constraint_name
),
keyed_pairs AS (
    SELECT
        a.owner,
        a.table_name,
        a.constraint_name AS constraint_1,
        a.constraint_type AS type_1,
        a.status AS status_1,
        b.constraint_name AS constraint_2,
        b.constraint_type AS type_2,
        b.status AS status_2,
        a.col_list_set
            || CASE
                   WHEN a.constraint_type = 'R' THEN
                       ' -> ' || a.r_owner || '.' || a.r_constraint_name
                       || CASE
                              WHEN b.r_owner || '.' || b.r_constraint_name
                                 <> a.r_owner || '.' || a.r_constraint_name
                              THEN ' / ' || b.r_owner || '.' || b.r_constraint_name
                          END
               END AS details,
        CASE
            WHEN a.constraint_type IN ('P', 'U')
             AND b.constraint_type IN ('P', 'U')
             AND a.constraint_type <> b.constraint_type
            THEN 'PK AND UNIQUE ON SAME COLUMNS'
            WHEN a.constraint_type IN ('P', 'U')
             AND b.constraint_type IN ('P', 'U')
            THEN 'DUPLICATE UNIQUE/PK'
            WHEN a.constraint_type = 'R'
             AND b.constraint_type = 'R'
             AND a.r_owner = b.r_owner
             AND a.r_constraint_name = b.r_constraint_name
            THEN 'DUPLICATE FOREIGN KEY (SAME PARENT)'
            WHEN a.constraint_type = 'R'
             AND b.constraint_type = 'R'
            THEN 'DUPLICATE FOREIGN KEY (SAME COLUMNS)'
        END AS redundancy
    FROM keyed a
    JOIN keyed b
      ON a.owner = b.owner
     AND a.table_name = b.table_name
     AND a.col_list_set = b.col_list_set
     AND a.constraint_name < b.constraint_name
     AND (
            (a.constraint_type IN ('P', 'U') AND b.constraint_type IN ('P', 'U'))
         OR (a.constraint_type = 'R' AND b.constraint_type = 'R')
         )
),
checks AS (
    SELECT
        c.owner,
        c.table_name,
        c.constraint_name,
        c.constraint_type,
        c.status,
        c.search_condition_vc,
        UPPER(REGEXP_REPLACE(TRIM(c.search_condition_vc), '\s+', ' ')) AS condition_norm
    FROM dba_constraints c
    JOIN dba_users u
      ON u.username = c.owner
    WHERE c.constraint_type = 'C'
      AND c.search_condition_vc IS NOT NULL
      AND u.oracle_maintained = 'N'
      AND c.table_name NOT LIKE 'BIN$%'
      AND (:cons_owner = '%' OR c.owner = :cons_owner)
),
check_pairs AS (
    SELECT
        a.owner,
        a.table_name,
        a.constraint_name AS constraint_1,
        a.constraint_type AS type_1,
        a.status AS status_1,
        b.constraint_name AS constraint_2,
        b.constraint_type AS type_2,
        b.status AS status_2,
        a.search_condition_vc AS details,
        'DUPLICATE CHECK CONSTRAINT' AS redundancy
    FROM checks a
    JOIN checks b
      ON a.owner = b.owner
     AND a.table_name = b.table_name
     AND a.condition_norm = b.condition_norm
     AND a.constraint_name < b.constraint_name
)
SELECT
    owner,
    table_name,
    constraint_1,
    type_1,
    status_1,
    constraint_2,
    type_2,
    status_2,
    details,
    redundancy
FROM keyed_pairs
UNION ALL
SELECT
    owner,
    table_name,
    constraint_1,
    type_1,
    status_1,
    constraint_2,
    type_2,
    status_2,
    details,
    redundancy
FROM check_pairs
ORDER BY owner, table_name, redundancy, constraint_1, constraint_2;

COLUMN owner CLEAR
COLUMN table_name CLEAR
COLUMN constraint_1 CLEAR
COLUMN type_1 CLEAR
COLUMN status_1 CLEAR
COLUMN constraint_2 CLEAR
COLUMN type_2 CLEAR
COLUMN status_2 CLEAR
COLUMN details CLEAR
COLUMN redundancy CLEAR

UNDEFINE p_owner
UNDEFINE 1

SET FEEDBACK ON
SET VERIFY ON
SET NULL ''
