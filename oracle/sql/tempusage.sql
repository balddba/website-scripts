/*******************************************************************************
*
* Script Name: tempusage.sql
* Title: Temporary tablespace usage
* Tags: Capacity, Temp
* Purpose: Monitor temporary tablespace usage across RAC instances
*
* Description:
*   Reports instance-level temp usage, current session consumers, top SQL,
*   tempfile configuration, sort operations, and high-usage alerts.
*   Shows NO DATA FOUND when a section has no rows. Requires Oracle 19c or
*   higher.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on GV$ views
*
* Output Format:
*   - Formatted reports with column headers and section breaks
*   - Instance summary, session usage, top SQL, files, sorts, and alerts
*
* Example Usage:
*   @tempusage.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET LINESIZE 200
SET PAGESIZE 500
SET FEEDBACK OFF
SET VERIFY OFF

-- Column formatting
COLUMN inst_id FORMAT 999 HEADING "Inst|ID"
COLUMN tablespace_name FORMAT A20 HEADING "Tablespace Name"
COLUMN usage_percentage FORMAT A8 HEADING "Usage %"
COLUMN status FORMAT A35 HEADING "Status"
COLUMN recommendation FORMAT A40 HEADING "Recommendation"
COLUMN username FORMAT A15 HEADING "Username"
COLUMN sid FORMAT 99999 HEADING "SID"
COLUMN serial# FORMAT 99999 HEADING "Serial#"
COLUMN program FORMAT A20 TRUNCATED HEADING "Program"
COLUMN machine FORMAT A20 TRUNCATED HEADING "Machine"
COLUMN temp_mb_used FORMAT 999,999.99 HEADING "Temp Usage|MB"
COLUMN tablespace FORMAT A15 HEADING "Tablespace"
COLUMN segtype FORMAT A10 HEADING "Seg Type"
COLUMN sql_id FORMAT A13 HEADING "SQL ID"
COLUMN file_name FORMAT A50 HEADING "Temporary File Name"
COLUMN size_mb FORMAT 999,999.99 HEADING "Size (MB)"
COLUMN parsing_schema_name FORMAT A32 HEADING "Schema Name"
COLUMN module FORMAT A30 HEADING "Module"
COLUMN executions FORMAT 999,999 HEADING "Exec|Count"
COLUMN mb_per_exec FORMAT 990.99 HEADING "MB Per|Exec"
COLUMN sql_text FORMAT A50 WORD_WRAPPED HEADING "SQL Text"


-- 1. Instance-Level Temp Usage Summary
PROMPT
PROMPT Temporary Tablespace Usage by Instance
PROMPT ====================================
WITH temp_usage AS (
  SELECT vt.inst_id,
         vt.name as tablespace_name,
         SUM(vtf.bytes)/1024/1024 total_mb,
         NVL(SUM(h.bytes_used)/1024/1024, 0) used_mb
  FROM gv$tablespace vt
  JOIN gv$tempfile vtf ON vt.ts# = vtf.ts#
       AND vt.inst_id = vtf.inst_id
  LEFT JOIN gv$temp_space_header h ON vt.name = h.tablespace_name
       AND vt.inst_id = h.inst_id
  GROUP BY vt.inst_id, vt.name
)
SELECT inst_id,
       tablespace_name,
       ROUND(total_mb,2) total_mb,
       ROUND(used_mb,2) used_mb,
       ROUND(total_mb - used_mb,2) free_mb,
       ROUND(used_mb/NULLIF(total_mb,0)*100,2) pct_used
FROM temp_usage
ORDER BY inst_id, tablespace_name;

-- 2. Current Session Temp Usage
PROMPT
PROMPT Current Session Temp Space Usage (All Instances)
PROMPT =============================================
SELECT s.inst_id,
       s.username,
       s.sid,
       s.serial#,
       s.program,
       s.machine,
       ROUND(tu.blocks*8192/1024/1024,2) temp_mb_used,
       tu.tablespace,
       tu.segtype,
       s.sql_id
FROM gv$tempseg_usage tu
JOIN gv$session s ON tu.session_addr = s.saddr
     AND tu.inst_id = s.inst_id
WHERE blocks > 0
ORDER BY blocks DESC;

-- 3. SQL Using Temp Space
PROMPT
PROMPT Top SQL Using Temp Space (Last Hour, All Instances)
PROMPT ===============================================
SELECT inst_id,
       sql_id,
       parsing_schema_name,
       module,
       SHARABLE_MEM/1024/1024 temp_mb_used,
       executions,
       ROUND(SHARABLE_MEM/1024/1024/NULLIF(executions,0),2) mb_per_exec,
       sql_text
FROM gv$sql
WHERE SHARABLE_MEM > 0
  AND last_active_time > SYSDATE - 1/24
ORDER BY SHARABLE_MEM DESC
FETCH FIRST 20 ROWS ONLY;

-- SELECT s.inst_id,
--        s.sql_id,
--        s.parsing_schema_name,
--        s.module,
--        w.actual_mem_used/1024/1024 mem_mb_used,
--        w.tempseg_size/1024/1024 temp_mb_used,
--        s.executions,
--        ROUND(w.tempseg_size/1024/1024/NULLIF(s.executions,0),2) mb_per_exec,
--        s.sql_text
-- FROM gv$sql s
-- JOIN gv$sql_workarea w ON s.sql_id = w.sql_id
--      AND s.inst_id = w.inst_id
-- WHERE w.tempseg_size > 0
--   AND s.last_active_time > SYSDATE - 1/24
-- ORDER BY w.tempseg_size DESC
-- FETCH FIRST 20 ROWS ONLY;

-- 4. Temp Space Configuration

PROMPT
PROMPT Temporary Tablespace Configuration (All Instances)
PROMPT ============================================
SELECT
    tf.inst_id,
    tf.name as file_name,
    ROUND(tf.bytes/1024/1024,2) size_mb
FROM gv$tempfile tf
ORDER BY tf.inst_id, tf.name;

COLUMN inst_id CLEAR
COLUMN file_name CLEAR
COLUMN size_mb CLEAR


-- 5. Sort Operation Analysis
PROMPT
PROMPT Sort Operation Analysis by Instance
PROMPT ================================
SELECT inst_id,
       tablespace,
       segtype,
       COUNT(*) operation_count,
       ROUND(AVG(blocks*8192/1024/1024),2) avg_mb_per_op,
       ROUND(MAX(blocks*8192/1024/1024),2) max_mb_per_op
FROM gv$tempseg_usage
GROUP BY inst_id, tablespace, segtype
ORDER BY inst_id, operation_count DESC;

-- 6. Instance-Level Alerts
PROMPT
PROMPT Temporary Space Alerts by Instance
PROMPT ===============================
WITH instance_usage AS (
  SELECT inst_id,
         tablespace_name,
         total_mb,
         used_mb,
         ROUND((used_mb/total_mb)*100,2) usage_pct
  FROM (
    SELECT tf.inst_id,
           tf.name as tablespace_name,  -- Changed from tf.tablespace_name to tf.name
           SUM(tf.bytes)/1024/1024 total_mb,
           NVL(SUM(th.bytes_used)/1024/1024,0) used_mb
    FROM gv$tempfile tf
    LEFT JOIN gv$temp_space_header th
    ON tf.inst_id = th.inst_id
       AND tf.name = th.tablespace_name  -- Changed from tf.tablespace_name to tf.name
    GROUP BY tf.inst_id, tf.name         -- Changed from tf.tablespace_name to tf.name
  )
)
SELECT inst_id,
       tablespace_name,
       usage_pct || '%' as usage_percentage,
       CASE
         WHEN usage_pct >= 90 THEN 'CRITICAL - Immediate action required'
         WHEN usage_pct >= 75 THEN 'WARNING - Monitor closely'
         WHEN usage_pct >= 50 THEN 'NOTICE - Above normal usage'
         ELSE 'OK - Normal range'
       END status,
       CASE
         WHEN usage_pct >= 90 THEN 'Consider adding tempfile or increasing size'
         WHEN usage_pct >= 75 THEN 'Plan for space increase if trend continues'
         WHEN usage_pct >= 50 THEN 'Review large temp space consumers'
         ELSE 'No action needed'
       END recommendation
FROM instance_usage
ORDER BY inst_id, usage_pct DESC;

-- Reset all column formatting
COLUMN inst_id CLEAR
COLUMN tablespace_name CLEAR
COLUMN usage_percentage CLEAR
COLUMN status CLEAR
COLUMN recommendation CLEAR
COLUMN username CLEAR
COLUMN sid CLEAR
COLUMN serial# CLEAR
COLUMN program CLEAR
COLUMN machine CLEAR
COLUMN temp_mb_used CLEAR
COLUMN tablespace CLEAR
COLUMN segtype CLEAR
COLUMN sql_id CLEAR
COLUMN file_name CLEAR
COLUMN size_mb CLEAR
COLUMN parsing_schema_name CLEAR
COLUMN module CLEAR
COLUMN executions CLEAR
COLUMN mb_per_exec CLEAR
COLUMN sql_text CLEAR


SET FEEDBACK ON
SET VERIFY ON