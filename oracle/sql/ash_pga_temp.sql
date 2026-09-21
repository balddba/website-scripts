/*******************************************************************************
*
* Script Name: ash_pga_temp.sql
* Title: ASH PGA and Temp Usage
* Tags: Performance, Memory, ASH
* Purpose: Identifies sessions and SQL queries consuming the highest PGA and Temp space from gv$active_session_history (pga_allocated, temp_space_allocated)
*
* Description:
*   Queries GV$ACTIVE_SESSION_HISTORY to report sessions and SQL queries with the
*   highest allocated PGA memory and temporary tablespace usage over a specified
*   time window. Helps identify memory-intensive operations and temp space hogs.
*
* Parameters:
*   &1 - (Optional) Time window in minutes to look back. Default 15.
*
* Required Privileges:
*   - SELECT on GV$ACTIVE_SESSION_HISTORY
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Instance ID
*   - Session ID and Serial#
*   - SQL ID
*   - SQL Operation Name
*   - Max PGA Allocated (MB)
*   - Max Temp Space Allocated (MB)
*   - Avg PGA Allocated (MB)
*   - Avg Temp Space Allocated (MB)
*   - Sample Count
*
* Example Usage:
*   sqlplus user/password@yourdb @ash_pga_temp.sql
*   sqlplus user/password@yourdb @ash_pga_temp.sql 30
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

COLUMN c_mins NEW_VALUE p_mins NOPRINT
SELECT NVL(NULLIF(TRIM('&1'), ''), '15') AS c_mins FROM dual;

COLUMN inst_id         FORMAT 999             HEADING 'Inst'
COLUMN session_id      FORMAT 99999           HEADING 'SID'
COLUMN session_serial# FORMAT 99999999        HEADING 'Serial#'
COLUMN sql_id          FORMAT A13             HEADING 'SQL ID'
COLUMN sql_opname      FORMAT A15 TRUNC       HEADING 'SQL Op'
COLUMN max_pga_mb      FORMAT 999,999,990.00  HEADING 'Max PGA MB'
COLUMN max_temp_mb     FORMAT 999,999,990.00  HEADING 'Max Temp MB'
COLUMN avg_pga_mb      FORMAT 999,999,990.00  HEADING 'Avg PGA MB'
COLUMN avg_temp_mb     FORMAT 999,999,990.00  HEADING 'Avg Temp MB'
COLUMN sample_count    FORMAT 999,999         HEADING 'Samples'

PROMPT
PROMPT === Top PGA and Temp Space Consumers from ASH (Last &&p_mins minutes) ===
PROMPT

SELECT *
FROM (
    SELECT
        inst_id,
        session_id,
        session_serial#,
        sql_id,
        sql_opname,
        ROUND(MAX(pga_allocated) / 1024 / 1024, 2) AS max_pga_mb,
        ROUND(MAX(temp_space_allocated) / 1024 / 1024, 2) AS max_temp_mb,
        ROUND(AVG(pga_allocated) / 1024 / 1024, 2) AS avg_pga_mb,
        ROUND(AVG(temp_space_allocated) / 1024 / 1024, 2) AS avg_temp_mb,
        COUNT(*) AS sample_count
    FROM gv$active_session_history
    WHERE sample_time >= SYSTIMESTAMP - NUMTODSINTERVAL(TO_NUMBER('&&p_mins'), 'MINUTE')
      AND (pga_allocated > 0 OR temp_space_allocated > 0)
    GROUP BY
        inst_id,
        session_id,
        session_serial#,
        sql_id,
        sql_opname
    ORDER BY max_pga_mb DESC, max_temp_mb DESC
)
WHERE ROWNUM <= 50;

COLUMN c_mins CLEAR
COLUMN inst_id CLEAR
COLUMN session_id CLEAR
COLUMN session_serial# CLEAR
COLUMN sql_id CLEAR
COLUMN sql_opname CLEAR
COLUMN max_pga_mb CLEAR
COLUMN max_temp_mb CLEAR
COLUMN avg_pga_mb CLEAR
COLUMN avg_temp_mb CLEAR
COLUMN sample_count CLEAR

SET FEEDBACK ON
SET VERIFY ON
