/*******************************************************************************
*
* Script Name: segment_space.sql
* Title: Segment and extent space
* Tags: Storage, Segments
* Purpose: Show allocated space for a segment, with optional per-extent detail
*
* Description:
*   Looks up DBA_SEGMENTS for owner, name, type, tablespace, bytes, blocks,
*   extents, and next extent. Pass EXTENT as the mode to list DBA_EXTENTS
*   (extent_id, file_id, block_id, bytes, blocks). Partition_name is optional;
*   omit it to include every partition of a partitioned segment. Press Enter
*   at the SQL*Plus prompt for unused optional arguments.
*
* Parameters:
*   &1 - Required owner, or OWNER.SEGMENT_NAME
*   &2 - Segment name when &1 is owner only; otherwise optional partition
*        or SEGMENT|EXTENT
*   &3 - Optional partition_name, or SEGMENT|EXTENT
*   &4 - Optional mode: SEGMENT | EXTENT (default SEGMENT)
*
* Required Privileges:
*   - SELECT on DBA_SEGMENTS
*   - SELECT on DBA_EXTENTS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Segment owner, name, partition, type, and tablespace
*   - Bytes, blocks, extents, next extent, header file and block
*   - Extent map when mode is EXTENT
*
* Example Usage:
*   SQL> @segment_space.sql HR EMPLOYEES
*   SQL> @segment_space.sql HR.EMPLOYEES
*   SQL> @segment_space.sql HR.EMPLOYEES EXTENT
*   SQL> @segment_space.sql HR SALES P2024
*   SQL> @segment_space.sql HR.SALES P2024 EXTENT
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
SET NULL '(null)'

COLUMN c_arg1 NEW_VALUE p_arg1 NOPRINT
COLUMN c_arg2 NEW_VALUE p_arg2 NOPRINT
COLUMN c_arg3 NEW_VALUE p_arg3 NOPRINT
COLUMN c_arg4 NEW_VALUE p_arg4 NOPRINT
SELECT
    TRIM('&1') AS c_arg1,
    TRIM('&2') AS c_arg2,
    TRIM('&3') AS c_arg3,
    TRIM('&4') AS c_arg4
FROM dual;

VARIABLE seg_owner      VARCHAR2(128)
VARIABLE seg_name       VARCHAR2(128)
VARIABLE partition_name VARCHAR2(128)
VARIABLE space_mode     VARCHAR2(10)

DECLARE
    l_a1   VARCHAR2(261) := UPPER(TRIM('&&p_arg1'));
    l_a2   VARCHAR2(128) := NULLIF(UPPER(TRIM('&&p_arg2')), '');
    l_a3   VARCHAR2(128) := NULLIF(UPPER(TRIM('&&p_arg3')), '');
    l_a4   VARCHAR2(128) := NULLIF(UPPER(TRIM('&&p_arg4')), '');
    l_owner VARCHAR2(128);
    l_name  VARCHAR2(128);
    l_part  VARCHAR2(128);
    l_mode  VARCHAR2(10);
    l_dot   PLS_INTEGER;
    l_cnt   PLS_INTEGER;

    PROCEDURE take_token(
        p_token IN VARCHAR2,
        p_part  IN OUT VARCHAR2,
        p_mode  IN OUT VARCHAR2
    ) IS
    BEGIN
        IF p_token IS NULL THEN
            RETURN;
        ELSIF p_token IN ('SEGMENT', 'EXTENT') THEN
            p_mode := p_token;
        ELSIF p_part IS NULL THEN
            p_part := p_token;
        ELSE
            RAISE_APPLICATION_ERROR(
                -20001,
                'Unexpected argument "' || p_token
                    || '". Use OWNER SEGMENT [PARTITION] [SEGMENT|EXTENT].'
            );
        END IF;
    END take_token;
BEGIN
    IF l_a1 IS NULL THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Segment is required: OWNER SEGMENT_NAME or OWNER.SEGMENT_NAME.'
        );
    END IF;

    l_dot := INSTR(l_a1, '.');
    IF l_dot > 0 THEN
        IF l_dot = 1
           OR l_dot = LENGTH(l_a1)
           OR INSTR(l_a1, '.', l_dot + 1) > 0 THEN
            RAISE_APPLICATION_ERROR(
                -20001,
                'Object must be OWNER.SEGMENT_NAME or OWNER plus SEGMENT_NAME.'
            );
        END IF;
        l_owner := SUBSTR(l_a1, 1, l_dot - 1);
        l_name  := SUBSTR(l_a1, l_dot + 1);
        take_token(l_a2, l_part, l_mode);
        take_token(l_a3, l_part, l_mode);
        take_token(l_a4, l_part, l_mode);
    ELSE
        IF l_a2 IS NULL OR l_a2 IN ('SEGMENT', 'EXTENT') THEN
            RAISE_APPLICATION_ERROR(
                -20001,
                'Segment name is required after owner, or use OWNER.SEGMENT_NAME.'
            );
        END IF;
        l_owner := l_a1;
        l_name  := l_a2;
        take_token(l_a3, l_part, l_mode);
        take_token(l_a4, l_part, l_mode);
    END IF;

    l_mode := NVL(l_mode, 'SEGMENT');

    SELECT COUNT(*)
    INTO l_cnt
    FROM dba_segments s
    WHERE s.owner = l_owner
      AND s.segment_name = l_name
      AND (l_part IS NULL OR s.partition_name = l_part);

    IF l_cnt = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Segment ' || l_owner || '.' || l_name
                || CASE
                       WHEN l_part IS NOT NULL THEN ' partition ' || l_part
                       ELSE ''
                   END
                || ' was not found in DBA_SEGMENTS.'
        );
    END IF;

    :seg_owner      := l_owner;
    :seg_name       := l_name;
    :partition_name := l_part;
    :space_mode     := l_mode;
END;
/

COLUMN owner           FORMAT A20               HEADING 'Owner'
COLUMN segment_name    FORMAT A30               HEADING 'Segment'
COLUMN partition_name  FORMAT A30               HEADING 'Partition'
COLUMN segment_type    FORMAT A24               HEADING 'Type'
COLUMN tablespace_name FORMAT A24               HEADING 'Tablespace'
COLUMN bytes           FORMAT 999,999,999,990   HEADING 'Bytes'
COLUMN size_mb         FORMAT 999,999,990.0     HEADING 'Size MB'
COLUMN blocks          FORMAT 999,999,990       HEADING 'Blocks'
COLUMN extents         FORMAT 999,990           HEADING 'Extents'
COLUMN next_extent     FORMAT 999,999,999,990   HEADING 'Next Extent'
COLUMN header_file     FORMAT 9999              HEADING 'Hdr File'
COLUMN header_block    FORMAT 999,999,990       HEADING 'Hdr Block'
COLUMN extent_id       FORMAT 999,990           HEADING 'Ext#'
COLUMN file_id         FORMAT 9999              HEADING 'File#'
COLUMN block_id        FORMAT 999,999,990       HEADING 'Block#'
COLUMN relative_fno    FORMAT 9999              HEADING 'Rel Fno'

PROMPT
PROMPT === Segment space (&p_arg1 &p_arg2) ===
PROMPT

SELECT
    s.owner,
    s.segment_name,
    s.partition_name,
    s.segment_type,
    s.tablespace_name,
    s.bytes,
    ROUND(s.bytes / 1024 / 1024, 1) AS size_mb,
    s.blocks,
    s.extents,
    s.next_extent,
    s.header_file,
    s.header_block
FROM dba_segments s
WHERE s.owner = :seg_owner
  AND s.segment_name = :seg_name
  AND (:partition_name IS NULL OR s.partition_name = :partition_name)
ORDER BY
    s.partition_name NULLS FIRST,
    s.segment_type,
    s.tablespace_name;

PROMPT
PROMPT === Extent map ===
PROMPT

SELECT
    e.owner,
    e.segment_name,
    e.partition_name,
    e.segment_type,
    e.tablespace_name,
    e.extent_id,
    e.file_id,
    e.block_id,
    e.relative_fno,
    e.bytes,
    e.blocks
FROM dba_extents e
WHERE e.owner = :seg_owner
  AND e.segment_name = :seg_name
  AND (:partition_name IS NULL OR e.partition_name = :partition_name)
  AND :space_mode = 'EXTENT'
ORDER BY
    e.partition_name NULLS FIRST,
    e.extent_id,
    e.file_id,
    e.block_id;

COLUMN owner CLEAR
COLUMN segment_name CLEAR
COLUMN partition_name CLEAR
COLUMN segment_type CLEAR
COLUMN tablespace_name CLEAR
COLUMN bytes CLEAR
COLUMN size_mb CLEAR
COLUMN blocks CLEAR
COLUMN extents CLEAR
COLUMN next_extent CLEAR
COLUMN header_file CLEAR
COLUMN header_block CLEAR
COLUMN extent_id CLEAR
COLUMN file_id CLEAR
COLUMN block_id CLEAR
COLUMN relative_fno CLEAR
COLUMN c_arg1 CLEAR
COLUMN c_arg2 CLEAR
COLUMN c_arg3 CLEAR
COLUMN c_arg4 CLEAR

SET NULL ''
SET FEEDBACK ON
SET VERIFY ON
