/*******************************************************************************
*
* Script Name: logswitches.sql
* Title: Log switch matrix
* Tags: Redo, Diagnostics
* Purpose: Display Oracle log switch activity by hour and date
*
* Description:
*   Shows a matrix of log switches for each hour of the day. Dates (MMDD)
*   are on the left and hours (00-23) across the top. Each cell is the
*   switch count for that hour.
*
* Parameters:
*   &1 - (Optional) Number of days of history to display. Default: 7
*
* Required Privileges:
*   - SELECT on V$LOG_HISTORY
*
* Output Format:
*   - MMDD date column
*   - Hour columns 00-23 with right-aligned two-digit counts
*
* Example Usage:
*   @logswitches.sql       -- Shows last 7 days of log switches
*   @logswitches.sql 14    -- Shows last 14 days of log switches
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

-- Accept variable for days, default to 7 if not specified.
COLUMN c_days NEW_VALUE days_limit NOPRINT
SELECT NVL(CAST(TRIM('&1') AS VARCHAR2(128)), '7') AS c_days
FROM dual;

set linesize 200
set pagesize 500
set feedback off
set verify off

PROMPT
PROMPT Log Switch Activity Matrix
PROMPT ========================
PROMPT

SELECT TO_CHAR(first_time, 'MMDD')                                         MMDD,
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '00', 1, 0)), '999') "00",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '01', 1, 0)), '999') "01",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '02', 1, 0)), '999') "02",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '03', 1, 0)), '999') "03",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '04', 1, 0)), '999') "04",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '05', 1, 0)), '999') "05",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '06', 1, 0)), '999') "06",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '07', 1, 0)), '999') "07",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '08', 1, 0)), '999') "08",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '09', 1, 0)), '999') "09",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '10', 1, 0)), '999') "10",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '11', 1, 0)), '999') "11",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '12', 1, 0)), '999') "12",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '13', 1, 0)), '999') "13",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '14', 1, 0)), '999') "14",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '15', 1, 0)), '999') "15",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '16', 1, 0)), '999') "16",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '17', 1, 0)), '999') "17",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '18', 1, 0)), '999') "18",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '19', 1, 0)), '999') "19",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '20', 1, 0)), '999') "20",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '21', 1, 0)), '999') "21",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '22', 1, 0)), '999') "22",
       TO_CHAR(SUM(DECODE(TO_CHAR(first_time, 'HH24'), '23', 1, 0)), '999') "23"
FROM v$log_history
WHERE first_time >= SYSDATE - &&days_limit
GROUP BY TO_CHAR(first_time, 'MMDD')
ORDER BY 1
/

PROMPT
PROMPT Hourly Statistics
PROMPT ================

WITH hourly_stats AS (
  SELECT TO_CHAR(first_time, 'HH24') AS hour,
         COUNT(*) AS switches,
         ROUND(COUNT(*) / &&days_limit, 1) AS avg_per_day,
         MAX(COUNT(*)) OVER () AS max_switches
  FROM v$log_history
  WHERE first_time >= SYSDATE - &&days_limit
  GROUP BY TO_CHAR(first_time, 'HH24')
)
SELECT hour || ':00' AS "Hour",
       switches AS "Total Switches",
       avg_per_day AS "Avg Per Day",
       RPAD('*', ROUND(switches*20/max_switches), '*') AS "Activity Graph"
FROM hourly_stats
ORDER BY hour;

PROMPT
PROMPT Time Period Analysis
PROMPT ==================

WITH period_stats AS (
  SELECT
    CASE
      WHEN TO_NUMBER(TO_CHAR(first_time, 'HH24')) BETWEEN 0 AND 5 THEN 'Night (00-05)'
      WHEN TO_NUMBER(TO_CHAR(first_time, 'HH24')) BETWEEN 6 AND 11 THEN 'Morning (06-11)'
      WHEN TO_NUMBER(TO_CHAR(first_time, 'HH24')) BETWEEN 12 AND 17 THEN 'Afternoon (12-17)'
      ELSE 'Evening (18-23)'
    END AS period,
    COUNT(*) AS switches
  FROM v$log_history
  WHERE first_time >= SYSDATE - &&days_limit
  GROUP BY
    CASE
      WHEN TO_NUMBER(TO_CHAR(first_time, 'HH24')) BETWEEN 0 AND 5 THEN 'Night (00-05)'
      WHEN TO_NUMBER(TO_CHAR(first_time, 'HH24')) BETWEEN 6 AND 11 THEN 'Morning (06-11)'
      WHEN TO_NUMBER(TO_CHAR(first_time, 'HH24')) BETWEEN 12 AND 17 THEN 'Afternoon (12-17)'
      ELSE 'Evening (18-23)'
    END
)
SELECT period,
       switches AS "Total Switches",
       ROUND(switches/&&days_limit, 1) AS "Avg Per Day",
       ROUND(RATIO_TO_REPORT(switches) OVER () * 100, 1) || '%' AS "% of Total"
FROM period_stats
ORDER BY
  CASE period
    WHEN 'Night (00-05)' THEN 1
    WHEN 'Morning (06-11)' THEN 2
    WHEN 'Afternoon (12-17)' THEN 3
    ELSE 4
  END;

PROMPT
PROMPT Peak Activity Analysis
PROMPT ===================

WITH hourly_peaks AS (
  SELECT TO_CHAR(first_time, 'MMDD') AS date_mmdd,
         TO_CHAR(first_time, 'HH24') AS hour,
         COUNT(*) AS switches,
         AVG(COUNT(*)) OVER (PARTITION BY TO_CHAR(first_time, 'HH24')) AS avg_switches,
         STDDEV(COUNT(*)) OVER (PARTITION BY TO_CHAR(first_time, 'HH24')) AS stddev_switches
  FROM v$log_history
  WHERE first_time >= SYSDATE - &&days_limit
  GROUP BY TO_CHAR(first_time, 'MMDD'), TO_CHAR(first_time, 'HH24')
)
SELECT date_mmdd || ' ' || hour || ':00' AS "DateTime",
       switches AS "Switches",
       ROUND(avg_switches, 1) AS "Hour Avg",
       CASE
         WHEN switches > avg_switches + 2*stddev_switches THEN 'HIGH ALERT'
         WHEN switches > avg_switches + stddev_switches THEN 'WARNING'
         ELSE 'Normal'
       END AS "Status"
FROM hourly_peaks
WHERE switches > avg_switches + stddev_switches
ORDER BY switches DESC;

PROMPT
PROMPT Daily Summary
PROMPT ============

SELECT TO_CHAR(first_time, 'MMDD') AS "Date",
       COUNT(*) AS "Total Switches",
       ROUND(COUNT(*)/24, 1) AS "Avg Per Hour",
       MIN(TO_CHAR(first_time, 'HH24')) || ':00' AS "First Switch",
       MAX(TO_CHAR(first_time, 'HH24')) || ':00' AS "Last Switch"
FROM v$log_history
WHERE first_time >= SYSDATE - &&days_limit
GROUP BY TO_CHAR(first_time, 'MMDD')
ORDER BY 1;

UNDEFINE days_limit
set feedback on
set verify on
