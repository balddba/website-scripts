/*******************************************************************************
*
* Script Name: sequence.sql
* Title: Sequence report
* Tags: Sequences, Schema
* Purpose: Display sequence settings, last number, and identity mapping for a schema or one sequence
*
* Description:
*   Reports every sequence in a schema, or one named sequence. LAST_NUMBER is
*   the highest value Oracle has allocated, which can be ahead of the last
*   value issued when CACHE is greater than zero. Identity-column sequences
*   are labeled with the table and column that own them.
*
* Parameters:
*   &1 - Target: SCHEMA, SCHEMA.%, or SCHEMA.SEQUENCE_NAME
*
* Required Privileges:
*   - SELECT on DBA_SEQUENCES
*   - SELECT on DBA_OBJECTS
*   - SELECT on DBA_TAB_IDENTITY_COLS
*
* Output Format:
*   - One row per sequence, sized for a 160-character terminal
*   - Owner, sequence name, min, max, increment, cycle, order, and cache
*   - Last allocated number, percent of range used, and remaining values
*   - Identity table.column when the sequence backs an identity column
*   - Object status
*
* Example Usage:
*   SQL> @sequence.sql HR
*   SQL> @sequence.sql HR.%
*   SQL> @sequence.sql HR.EMPLOYEES_SEQ
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
SET WRAP OFF

VARIABLE seq_owner VARCHAR2(128)
VARIABLE seq_name  VARCHAR2(128)

DECLARE
    l_target       VARCHAR2(261) := UPPER(TRIM('&1'));
    l_dot_position PLS_INTEGER;
    l_seq_count    PLS_INTEGER;
BEGIN
    -- SCHEMA lists every sequence; SCHEMA.NAME lists one sequence.
    l_dot_position := INSTR(l_target, '.');
    IF l_dot_position = 0 THEN
        :seq_owner := l_target;
        :seq_name  := '%';
    ELSIF l_dot_position = 1
       OR l_dot_position = LENGTH(l_target)
       OR INSTR(l_target, '.', l_dot_position + 1) > 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Target must be SCHEMA, SCHEMA.%, or SCHEMA.SEQUENCE_NAME.'
        );
    ELSE
        :seq_owner := SUBSTR(l_target, 1, l_dot_position - 1);
        :seq_name  := SUBSTR(l_target, l_dot_position + 1);
    END IF;

    -- Ordinary unquoted identifiers only; % is the schema-wide wildcard.
    IF NOT REGEXP_LIKE(:seq_owner, '^[A-Z][A-Z0-9_$#]*$')
       OR (:seq_name <> '%'
           AND NOT REGEXP_LIKE(:seq_name, '^[A-Z][A-Z0-9_$#]*$')) THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Schema and sequence must be ordinary Oracle identifiers; only % is supported as a wildcard.'
        );
    END IF;

    SELECT COUNT(*)
    INTO l_seq_count
    FROM dba_sequences
    WHERE sequence_owner = :seq_owner
      AND (:seq_name = '%' OR sequence_name = :seq_name);

    IF l_seq_count = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'No sequences found for ' || :seq_owner || '.' || :seq_name || '.'
        );
    END IF;
END;
/

COLUMN sequence_owner  FORMAT A18  HEADING 'Owner'
COLUMN sequence_name   FORMAT A24  HEADING 'Sequence'
COLUMN min_value       FORMAT A8   HEADING 'Min'
COLUMN max_value       FORMAT A10  HEADING 'Max'
COLUMN increment_by    FORMAT A5   HEADING 'Incr'
COLUMN cycle_flag      FORMAT A3   HEADING 'Cyc'
COLUMN order_flag      FORMAT A3   HEADING 'Ord'
COLUMN cache_size      FORMAT A5   HEADING 'Cache'
COLUMN last_number     FORMAT A12  HEADING 'Last Num'
COLUMN pct_used        FORMAT 990.0 HEADING 'Pct'
COLUMN remaining       FORMAT A10  HEADING 'Remain'
COLUMN identity_column FORMAT A22  HEADING 'Identity'
COLUMN status          FORMAT A7   HEADING 'Status'

SELECT
    s.sequence_owner,
    s.sequence_name,
    CASE
        WHEN ABS(s.min_value) >= POWER(10, 8)
        THEN TRIM(TO_CHAR(s.min_value, '9.99EEEE'))
        ELSE TO_CHAR(s.min_value, 'TM9')
    END AS min_value,
    CASE
        WHEN ABS(s.max_value) >= POWER(10, 10)
        THEN TRIM(TO_CHAR(s.max_value, '9.99EEEE'))
        ELSE TO_CHAR(s.max_value, 'TM9')
    END AS max_value,
    TO_CHAR(s.increment_by, 'TM9') AS increment_by,
    s.cycle_flag,
    s.order_flag,
    CASE
        WHEN s.cache_size = 0 THEN 'NONE'
        ELSE TO_CHAR(s.cache_size, 'TM9')
    END AS cache_size,
    -- LAST_NUMBER is the cache high-water mark, not necessarily the last issued value.
    CASE
        WHEN ABS(s.last_number) >= POWER(10, 12)
        THEN TRIM(TO_CHAR(s.last_number, '9.99EEEE'))
        ELSE TO_CHAR(s.last_number, 'TM9')
    END AS last_number,
    CASE
        WHEN s.max_value = s.min_value THEN NULL
        WHEN s.increment_by > 0 THEN
            ROUND(
                (s.last_number - s.min_value)
                / (s.max_value - s.min_value)
                * 100,
                1
            )
        ELSE
            ROUND(
                (s.min_value - s.last_number)
                / (s.min_value - s.max_value)
                * 100,
                1
            )
    END AS pct_used,
    -- Remaining values until wrap; meaningless for CYCLE sequences.
    CASE
        WHEN s.cycle_flag = 'Y' THEN NULL
        WHEN s.increment_by > 0
             AND (s.max_value - s.last_number) / s.increment_by >= POWER(10, 10)
        THEN TRIM(TO_CHAR(TRUNC((s.max_value - s.last_number) / s.increment_by), '9.99EEEE'))
        WHEN s.increment_by > 0
        THEN TO_CHAR(TRUNC((s.max_value - s.last_number) / s.increment_by), 'TM9')
        WHEN (s.last_number - s.min_value) / ABS(s.increment_by) >= POWER(10, 10)
        THEN TRIM(TO_CHAR(TRUNC((s.last_number - s.min_value) / ABS(s.increment_by)), '9.99EEEE'))
        ELSE TO_CHAR(TRUNC((s.last_number - s.min_value) / ABS(s.increment_by)), 'TM9')
    END AS remaining,
    CASE
        WHEN i.table_name IS NOT NULL THEN
            i.table_name || '.' || i.column_name
    END AS identity_column,
    o.status
FROM dba_sequences s
LEFT JOIN dba_objects o
  ON o.owner = s.sequence_owner
 AND o.object_name = s.sequence_name
 AND o.object_type = 'SEQUENCE'
LEFT JOIN dba_tab_identity_cols i
  ON i.owner = s.sequence_owner
 AND i.sequence_name = s.sequence_name
WHERE s.sequence_owner = :seq_owner
  AND (:seq_name = '%' OR s.sequence_name = :seq_name)
ORDER BY s.sequence_owner, s.sequence_name;

SET FEEDBACK ON
