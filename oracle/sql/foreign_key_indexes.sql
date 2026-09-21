/*******************************************************************************
*
* Script Name: foreign_key_indexes.sql
* Title: Foreign key index check
* Tags: Indexes, Constraints, Performance
* Purpose: Find foreign keys without a supporting child index, and referenced parent keys with a missing or unusable unique index
*
* Description:
*   A usable supporting index on the child table must lead with the foreign
*   key columns in constraint order (extra trailing index columns are fine).
*   Bitmap, invisible, unusable, and function-based indexes do not count.
*   Oracle requires a primary or unique constraint on the parent columns; this
*   script still flags a missing, unusable, invisible, or disabled parent
*   unique index. Oracle-maintained schemas and recycle-bin tables are skipped.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on DBA_CONSTRAINTS
*   - SELECT on DBA_CONS_COLUMNS
*   - SELECT on DBA_INDEXES
*   - SELECT on DBA_IND_COLUMNS
*   - SELECT on DBA_USERS
*
* Output Format:
*   - Child foreign keys missing a supporting index, with suggested CREATE INDEX
*   - Parent keys whose unique index is missing or not usable
*
* Example Usage:
*   SQL> @foreign_key_indexes.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET LINESIZE 280
SET PAGESIZE 100
SET FEEDBACK ON

COLUMN owner              FORMAT A20 HEADING 'Owner'
COLUMN table_name         FORMAT A30 HEADING 'Child Table'
COLUMN constraint_name    FORMAT A30 HEADING 'FK Name'
COLUMN fk_columns         FORMAT A40 HEADING 'FK Columns'
COLUMN parent_owner       FORMAT A20 HEADING 'Parent Owner'
COLUMN parent_table       FORMAT A30 HEADING 'Parent Table'
COLUMN parent_constraint  FORMAT A30 HEADING 'Parent Key'
COLUMN fk_status          FORMAT A9  HEADING 'FK Status'
COLUMN delete_rule        FORMAT A12 HEADING 'Delete Rule'
COLUMN suggested_index    FORMAT A90 HEADING 'Suggested Index'

PROMPT
PROMPT === Foreign keys missing a supporting child index ===
PROMPT

WITH fk_cols AS (
    SELECT
        c.owner,
        c.constraint_name,
        c.table_name,
        c.status AS fk_status,
        c.delete_rule,
        c.r_owner,
        c.r_constraint_name,
        cc.column_name,
        cc.position
    FROM dba_constraints c
    JOIN dba_cons_columns cc
      ON cc.owner = c.owner
     AND cc.constraint_name = c.constraint_name
    JOIN dba_users u
      ON u.username = c.owner
    WHERE c.constraint_type = 'R'
      AND u.oracle_maintained = 'N'
      AND c.table_name NOT LIKE 'BIN$%'
),
fk AS (
    SELECT
        owner,
        constraint_name,
        table_name,
        fk_status,
        delete_rule,
        r_owner,
        r_constraint_name,
        COUNT(*) AS col_cnt,
        LISTAGG(column_name, ', ') WITHIN GROUP (ORDER BY position) AS fk_columns
    FROM fk_cols
    GROUP BY
        owner,
        constraint_name,
        table_name,
        fk_status,
        delete_rule,
        r_owner,
        r_constraint_name
),
covered AS (
    SELECT
        f.owner,
        f.constraint_name
    FROM fk f
    JOIN dba_indexes i
      ON i.table_owner = f.owner
     AND i.table_name = f.table_name
     AND i.index_type IN ('NORMAL', 'NORMAL/REV', 'IOT - TOP')
     AND i.status IN ('VALID', 'N/A')
     AND NVL(i.visibility, 'VISIBLE') = 'VISIBLE'
    JOIN dba_ind_columns ic
      ON ic.index_owner = i.owner
     AND ic.index_name = i.index_name
    JOIN fk_cols fc
      ON fc.owner = f.owner
     AND fc.constraint_name = f.constraint_name
     AND fc.column_name = ic.column_name
     AND fc.position = ic.column_position
    GROUP BY
        f.owner,
        f.constraint_name,
        i.owner,
        i.index_name,
        f.col_cnt
    HAVING COUNT(*) = f.col_cnt
)
SELECT
    f.owner,
    f.table_name,
    f.constraint_name,
    f.fk_columns,
    r.owner AS parent_owner,
    r.table_name AS parent_table,
    f.r_constraint_name AS parent_constraint,
    f.fk_status,
    f.delete_rule,
    'CREATE INDEX ix_' || f.constraint_name
        || ' ON ' || f.owner || '.' || f.table_name
        || ' (' || f.fk_columns || ');' AS suggested_index
FROM fk f
JOIN dba_constraints r
  ON r.owner = f.r_owner
 AND r.constraint_name = f.r_constraint_name
WHERE NOT EXISTS (
    SELECT 1
    FROM covered c
    WHERE c.owner = f.owner
      AND c.constraint_name = f.constraint_name
)
ORDER BY f.owner, f.table_name, f.constraint_name;

COLUMN child_owner        FORMAT A20 HEADING 'Child Owner'
COLUMN child_table        FORMAT A30 HEADING 'Child Table'
COLUMN fk_name            FORMAT A30 HEADING 'FK Name'
COLUMN parent_type        FORMAT A6  HEADING 'Type'
COLUMN parent_status      FORMAT A9  HEADING 'PK Status'
COLUMN parent_columns     FORMAT A40 HEADING 'Parent Columns'
COLUMN index_owner        FORMAT A20 HEADING 'Index Owner'
COLUMN index_name         FORMAT A30 HEADING 'Index Name'
COLUMN index_status       FORMAT A10 HEADING 'Idx Status'
COLUMN visibility         FORMAT A10 HEADING 'Visible'
COLUMN problem            FORMAT A36 HEADING 'Problem'

PROMPT
PROMPT === Referenced parent keys with a missing or unusable unique index ===
PROMPT

WITH fk AS (
    SELECT DISTINCT
        c.owner,
        c.constraint_name,
        c.table_name,
        c.r_owner,
        c.r_constraint_name
    FROM dba_constraints c
    JOIN dba_users u
      ON u.username = c.owner
    WHERE c.constraint_type = 'R'
      AND u.oracle_maintained = 'N'
      AND c.table_name NOT LIKE 'BIN$%'
)
SELECT
    f.owner AS child_owner,
    f.table_name AS child_table,
    f.constraint_name AS fk_name,
    r.owner AS parent_owner,
    r.table_name AS parent_table,
    r.constraint_name AS parent_constraint,
    r.constraint_type AS parent_type,
    r.status AS parent_status,
    (
        SELECT LISTAGG(cc.column_name, ', ') WITHIN GROUP (ORDER BY cc.position)
        FROM dba_cons_columns cc
        WHERE cc.owner = r.owner
          AND cc.constraint_name = r.constraint_name
    ) AS parent_columns,
    r.index_owner,
    r.index_name,
    i.status AS index_status,
    i.visibility,
    CASE
        WHEN r.index_name IS NULL THEN 'NO INDEX ON PARENT CONSTRAINT'
        WHEN i.index_name IS NULL THEN 'INDEX NAME NOT FOUND'
        WHEN i.status = 'UNUSABLE' THEN 'INDEX UNUSABLE'
        WHEN NVL(i.visibility, 'VISIBLE') = 'INVISIBLE' THEN 'INDEX INVISIBLE'
        WHEN NVL(i.funcidx_status, 'ENABLED') = 'DISABLED' THEN 'FUNCTION-BASED INDEX DISABLED'
        ELSE 'INDEX PROBLEM'
    END AS problem
FROM fk f
JOIN dba_constraints r
  ON r.owner = f.r_owner
 AND r.constraint_name = f.r_constraint_name
LEFT JOIN dba_indexes i
  ON i.owner = NVL(r.index_owner, r.owner)
 AND i.index_name = r.index_name
WHERE r.index_name IS NULL
   OR i.index_name IS NULL
   OR i.status = 'UNUSABLE'
   OR NVL(i.visibility, 'VISIBLE') = 'INVISIBLE'
   OR NVL(i.funcidx_status, 'ENABLED') = 'DISABLED'
ORDER BY f.owner, f.table_name, f.constraint_name;
