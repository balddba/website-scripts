/*******************************************************************************
*
* Script Name: histograms.sql
* Title: Table column histograms
* Tags: Statistics, Histograms
* Purpose: Report histogram type, buckets, endpoints, and low/high values for a table
*
* Description:
*   Reads DBA_TAB_COL_STATISTICS for histogram type, bucket count, and stored
*   low/high values, then DBA_TAB_HISTOGRAMS for each endpoint. Pass a column
*   name to limit the report; omit it (or press Enter) to show every column
*   that has statistics. LOW_VALUE and HIGH_VALUE are displayed as RAW hex
*   plus a VARCHAR2/NUMBER decode when the column type allows it.
*
* Parameters:
*   &1 - Owner. Default: current USER
*   &2 - Table name (required)
*   &3 - (Optional) Column name. Default: all columns
*
* Required Privileges:
*   - SELECT on DBA_TABLES
*   - SELECT on DBA_TAB_COLUMNS
*   - SELECT on DBA_TAB_COL_STATISTICS
*   - SELECT on DBA_TAB_HISTOGRAMS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - One row per column: histogram type, buckets, distinct, nulls, low/high
*   - One row per histogram endpoint: endpoint number, value, actual value
*
* Example Usage:
*   SQL> @histograms.sql HR EMPLOYEES
*   SQL> @histograms.sql HR EMPLOYEES SALARY
*   SQL> @histograms.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 240
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF
SET WRAP OFF

-- Optional &1/&3: SQL*Plus prompts if omitted; Enter uses USER and all columns.
COLUMN c_owner  NEW_VALUE p_owner  NOPRINT
COLUMN c_table  NEW_VALUE p_table  NOPRINT
COLUMN c_column NEW_VALUE p_column NOPRINT
SELECT
    NVL(CAST(TRIM('&1') AS VARCHAR2(128)), USER) AS c_owner,
    CAST(TRIM('&2') AS VARCHAR2(128)) AS c_table,
    NVL(CAST(TRIM('&3') AS VARCHAR2(128)), '%') AS c_column
FROM dual;

VARIABLE object_owner VARCHAR2(128)
VARIABLE object_name  VARCHAR2(128)
VARIABLE column_name  VARCHAR2(128)

DECLARE
    l_owner       VARCHAR2(128) := UPPER(TRIM('&&p_owner'));
    l_table_name  VARCHAR2(128) := UPPER(TRIM('&&p_table'));
    l_column_name VARCHAR2(128) := UPPER(TRIM('&&p_column'));
    l_table_count PLS_INTEGER;
BEGIN
    IF l_table_name IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'Table name is required.');
    END IF;

    IF NOT REGEXP_LIKE(l_owner, '^[A-Z][A-Z0-9_$#]*$')
       OR NOT REGEXP_LIKE(l_table_name, '^[A-Z][A-Z0-9_$#]*$')
       OR (l_column_name <> '%'
           AND NOT REGEXP_LIKE(l_column_name, '^[A-Z][A-Z0-9_$#]*$')) THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Owner, table, and column must be ordinary Oracle identifiers.'
        );
    END IF;

    SELECT COUNT(*)
    INTO l_table_count
    FROM dba_tables
    WHERE owner = l_owner
      AND table_name = l_table_name;

    IF l_table_count = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'Table ' || l_owner || '.' || l_table_name || ' was not found.'
        );
    END IF;

    :object_owner := l_owner;
    :object_name  := l_table_name;
    :column_name  := l_column_name;
END;
/

COLUMN owner            FORMAT A20               HEADING 'Owner'
COLUMN table_name       FORMAT A30               HEADING 'Table'
COLUMN column_name      FORMAT A30               HEADING 'Column'
COLUMN data_type        FORMAT A16               HEADING 'Type'
COLUMN histogram        FORMAT A18               HEADING 'Histogram'
COLUMN num_buckets      FORMAT 999,990           HEADING 'Buckets'
COLUMN num_distinct     FORMAT 999,999,999,990   HEADING 'Distinct'
COLUMN num_nulls        FORMAT 999,999,999,990   HEADING 'Nulls'
COLUMN low_value        FORMAT A32 TRUNC         HEADING 'Low Value'
COLUMN high_value       FORMAT A32 TRUNC         HEADING 'High Value'
COLUMN low_raw          FORMAT A24 TRUNC         HEADING 'Low RAW'
COLUMN high_raw         FORMAT A24 TRUNC         HEADING 'High RAW'
COLUMN last_analyzed    FORMAT A19               HEADING 'Last Analyzed'
COLUMN endpoint_number  FORMAT 999,999,990       HEADING 'Endpoint #'
COLUMN endpoint_value   FORMAT 9999999999990.099 HEADING 'Endpoint Value'
COLUMN endpoint_actual_value FORMAT A40 TRUNC    HEADING 'Actual Value'

PROMPT
PROMPT === Column histogram summary ===
PROMPT

SELECT
    s.owner,
    s.table_name,
    s.column_name,
    c.data_type,
    s.histogram,
    s.num_buckets,
    s.num_distinct,
    s.num_nulls,
    CASE
        WHEN c.data_type IN ('VARCHAR2', 'CHAR', 'NVARCHAR2', 'NCHAR')
        THEN SUBSTR(UTL_RAW.CAST_TO_VARCHAR2(s.low_value), 1, 32)
        WHEN c.data_type IN ('NUMBER', 'FLOAT')
        THEN TO_CHAR(UTL_RAW.CAST_TO_NUMBER(s.low_value))
        ELSE RAWTOHEX(s.low_value)
    END AS low_value,
    CASE
        WHEN c.data_type IN ('VARCHAR2', 'CHAR', 'NVARCHAR2', 'NCHAR')
        THEN SUBSTR(UTL_RAW.CAST_TO_VARCHAR2(s.high_value), 1, 32)
        WHEN c.data_type IN ('NUMBER', 'FLOAT')
        THEN TO_CHAR(UTL_RAW.CAST_TO_NUMBER(s.high_value))
        ELSE RAWTOHEX(s.high_value)
    END AS high_value,
    RAWTOHEX(s.low_value) AS low_raw,
    RAWTOHEX(s.high_value) AS high_raw,
    TO_CHAR(s.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS last_analyzed
FROM dba_tab_col_statistics s
JOIN dba_tab_columns c
  ON c.owner = s.owner
 AND c.table_name = s.table_name
 AND c.column_name = s.column_name
WHERE s.owner = :object_owner
  AND s.table_name = :object_name
  AND (:column_name = '%' OR s.column_name = :column_name)
ORDER BY c.column_id, s.column_name;

PROMPT
PROMPT === Histogram endpoints ===
PROMPT Columns with histogram NONE have no endpoint rows.
PROMPT

SELECT
    h.owner,
    h.table_name,
    h.column_name,
    s.histogram,
    h.endpoint_number,
    h.endpoint_value,
    h.endpoint_actual_value
FROM dba_tab_histograms h
JOIN dba_tab_col_statistics s
  ON s.owner = h.owner
 AND s.table_name = h.table_name
 AND s.column_name = h.column_name
WHERE h.owner = :object_owner
  AND h.table_name = :object_name
  AND (:column_name = '%' OR h.column_name = :column_name)
ORDER BY h.column_name, h.endpoint_number;

UNDEFINE p_owner
UNDEFINE p_table
UNDEFINE p_column
UNDEFINE 1
UNDEFINE 2
UNDEFINE 3

SET FEEDBACK ON
SET VERIFY ON
