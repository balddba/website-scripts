/*******************************************************************************
*
* Script Name: redundant_indexes.sql
* Title: Redundant indexes
* Tags: Indexes, Tuning
* Purpose: Find indexes whose leading columns are a prefix of another index on the same table
*
* Description:
*   Compares DBA_IND_COLUMNS lists on each table. An index is reported when
*   its columns, in order, are a prefix of another index, or when two indexes
*   have the same column list. Unique indexes that are a prefix of a
*   non-unique index are still listed; they are not drop candidates for
*   uniqueness enforcement. Oracle-maintained schemas are skipped when the
*   owner filter is %. LOB, IOT, and domain indexes are ignored.
*
* Parameters:
*   &1 - (Optional) Owner. Default: all non-Oracle-maintained schemas
*
* Required Privileges:
*   - SELECT on DBA_INDEXES
*   - SELECT on DBA_IND_COLUMNS
*   - SELECT on DBA_USERS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Owner, table, redundant index and covering index
*   - Column lists and uniqueness for both indexes
*   - Note: KEEP UNIQUE, DUPLICATE, or PREFIX
*
* Example Usage:
*   SQL> @redundant_indexes.sql
*   SQL> @redundant_indexes.sql HR
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
SET WRAP OFF

-- Optional &1: SQL*Plus prompts if omitted; Enter means all non-Oracle schemas.
COLUMN c_owner NEW_VALUE p_owner NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), '%') AS c_owner FROM dual;

VARIABLE object_owner VARCHAR2(128)

DECLARE
    l_owner VARCHAR2(128) := UPPER(TRIM('&&p_owner'));
BEGIN
    IF l_owner <> '%'
       AND NOT REGEXP_LIKE(l_owner, '^[A-Z][A-Z0-9_$#]*$') THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Owner must be an ordinary Oracle identifier or %.'
        );
    END IF;

    :object_owner := l_owner;
END;
/

COLUMN table_owner             FORMAT A16  HEADING 'Owner'
COLUMN table_name              FORMAT A28  HEADING 'Table'
COLUMN redundant_index         FORMAT A30  HEADING 'Redundant Index'
COLUMN redundant_columns       FORMAT A40  HEADING 'Redundant Columns'
COLUMN redundant_uniqueness    FORMAT A10  HEADING 'Red. Unique'
COLUMN covering_index          FORMAT A30  HEADING 'Covering Index'
COLUMN covering_columns        FORMAT A40  HEADING 'Covering Columns'
COLUMN covering_uniqueness     FORMAT A10  HEADING 'Cov. Unique'
COLUMN note                    FORMAT A14  HEADING 'Note'

PROMPT
PROMPT === Redundant indexes ===
PROMPT PREFIX = leading columns match a wider index. DUPLICATE = same columns.
PROMPT KEEP UNIQUE = unique index is a prefix of a non-unique index; do not drop
PROMPT it if it enforces uniqueness.
PROMPT

WITH idx_cols AS (
    SELECT
        i.owner,
        i.index_name,
        i.table_owner,
        i.table_name,
        i.uniqueness,
        i.index_type,
        LISTAGG(ic.column_name, ', ')
            WITHIN GROUP (ORDER BY ic.column_position) AS col_list,
        COUNT(*) AS col_cnt
    FROM dba_indexes i
    JOIN dba_ind_columns ic
      ON ic.index_owner = i.owner
     AND ic.index_name = i.index_name
    JOIN dba_users u
      ON u.username = i.table_owner
    WHERE i.index_type IN (
            'NORMAL',
            'NORMAL/REV',
            'FUNCTION-BASED NORMAL',
            'BITMAP',
            'FUNCTION-BASED BITMAP'
          )
      AND NVL(i.dropped, 'NO') = 'NO'
      AND (
            (:object_owner = '%' AND u.oracle_maintained = 'N')
            OR i.table_owner = :object_owner
          )
    GROUP BY
        i.owner,
        i.index_name,
        i.table_owner,
        i.table_name,
        i.uniqueness,
        i.index_type
)
SELECT
    a.table_owner,
    a.table_name,
    a.index_name AS redundant_index,
    a.col_list AS redundant_columns,
    a.uniqueness AS redundant_uniqueness,
    b.index_name AS covering_index,
    b.col_list AS covering_columns,
    b.uniqueness AS covering_uniqueness,
    CASE
        WHEN a.col_cnt = b.col_cnt THEN 'DUPLICATE'
        WHEN a.uniqueness = 'UNIQUE' AND b.uniqueness = 'NONUNIQUE'
        THEN 'KEEP UNIQUE'
        ELSE 'PREFIX'
    END AS note
FROM idx_cols a
JOIN idx_cols b
  ON a.table_owner = b.table_owner
 AND a.table_name = b.table_name
 AND a.index_name <> b.index_name
 AND (
        (a.col_cnt < b.col_cnt
         AND b.col_list LIKE a.col_list || ', %')
        OR
        (a.col_cnt = b.col_cnt
         AND a.col_list = b.col_list
         AND a.index_name < b.index_name)
     )
ORDER BY
    a.table_owner,
    a.table_name,
    a.index_name,
    b.index_name;

UNDEFINE p_owner
UNDEFINE 1

SET FEEDBACK ON
SET VERIFY ON
