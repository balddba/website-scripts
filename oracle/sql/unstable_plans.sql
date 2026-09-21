/*******************************************************************************
*
* Script Name: unstable_plans.sql
* Title: Unstable SQL plans
* Tags: SQL, Plans, Performance
* Purpose: Find SQL statements with more than one plan hash and elapsed-time variance
*
* Description:
*   The V$SQL section needs no extra pack: it groups child cursors by SQL_ID
*   and PLAN_HASH_VALUE and lists statements that have more than one plan.
*   The AWR section reads DBA_HIST_SQLSTAT / DBA_HIST_SNAPSHOT for the same
*   pattern over a lookback window.
*
*   Oracle Diagnostic Pack (and Tuning Pack, if you use SQL Tuning Advisor
*   against the same data) is required to query AWR views. Do not run the AWR
*   section unless the database is licensed for Diagnostic Pack. Pass VSQL to
*   skip AWR, AWR to run only history, or ALL (default) to run both.
*
* Parameters:
*   &1 - (Optional) Source: VSQL, AWR, or ALL. Default ALL.
*   &2 - (Optional) AWR lookback days. Default 7. Ignored for VSQL.
*
* Required Privileges:
*   - SELECT on V$SQL
*   - SELECT on DBA_HIST_SQLSTAT (AWR section; Diagnostic Pack)
*   - SELECT on DBA_HIST_SNAPSHOT (AWR section; Diagnostic Pack)
*   - SELECT on DBA_HIST_SQLTEXT (AWR section; Diagnostic Pack)
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - SQL ID, plan hash, executions, elapsed per exec, buffer gets per exec
*   - Plan count and elapsed variance when more than one plan exists
*
* Example Usage:
*   SQL> @unstable_plans.sql
*   SQL> @unstable_plans.sql VSQL
*   SQL> @unstable_plans.sql AWR 3
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 220
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN c_source NEW_VALUE p_source NOPRINT
COLUMN c_days   NEW_VALUE p_days   NOPRINT
SELECT NVL(CAST(UPPER(TRIM('&1')) AS VARCHAR2(128)), 'ALL') AS c_source FROM dual;
SELECT NVL(CAST(TRIM('&2') AS VARCHAR2(128)), '7') AS c_days FROM dual;

VARIABLE run_vsql NUMBER
VARIABLE run_awr  NUMBER
VARIABLE lookback NUMBER

BEGIN
    IF '&&p_source' NOT IN ('VSQL', 'AWR', 'ALL') THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Source must be VSQL, AWR, or ALL.'
        );
    END IF;

    :run_vsql := CASE WHEN '&&p_source' IN ('VSQL', 'ALL') THEN 1 ELSE 0 END;
    :run_awr  := CASE WHEN '&&p_source' IN ('AWR', 'ALL') THEN 1 ELSE 0 END;
    :lookback := TO_NUMBER('&&p_days');
END;
/

COLUMN sql_id            FORMAT A13              HEADING 'SQL ID'
COLUMN plan_hash_value   FORMAT 9999999999       HEADING 'Plan Hash'
COLUMN plan_count        FORMAT 999              HEADING 'Plans'
COLUMN executions        FORMAT 999,999,999      HEADING 'Execs'
COLUMN elapsed_sec       FORMAT 999,999,990.3    HEADING 'Elapsed S'
COLUMN ela_per_exec      FORMAT 999,990.4        HEADING 'Ela/Exec'
COLUMN gets_per_exec     FORMAT 999,999,999,990  HEADING 'Gets/Exec'
COLUMN min_ela_per_exec  FORMAT 999,990.4        HEADING 'Min Ela'
COLUMN max_ela_per_exec  FORMAT 999,990.4        HEADING 'Max Ela'
COLUMN parsing_schema_name FORMAT A20            HEADING 'Schema'
COLUMN sql_text          FORMAT A50 TRUNC        HEADING 'SQL Text'

PROMPT
PROMPT === Unstable plans from V$SQL (no Diagnostic Pack required) ===
PROMPT

SELECT
    q.sql_id,
    q.plan_hash_value,
    p.plan_count,
    SUM(q.executions) AS executions,
    ROUND(SUM(q.elapsed_time) / 1e6, 3) AS elapsed_sec,
    ROUND(SUM(q.elapsed_time) / NULLIF(SUM(q.executions), 0) / 1e6, 4) AS ela_per_exec,
    ROUND(SUM(q.buffer_gets) / NULLIF(SUM(q.executions), 0), 0) AS gets_per_exec,
    ROUND(p.min_ela_per_exec, 4) AS min_ela_per_exec,
    ROUND(p.max_ela_per_exec, 4) AS max_ela_per_exec,
    MIN(q.parsing_schema_name) AS parsing_schema_name,
    MIN(q.sql_text) AS sql_text
FROM v$sql q
JOIN (
    SELECT
        sql_id,
        COUNT(DISTINCT plan_hash_value) AS plan_count,
        MIN(elapsed_time / NULLIF(executions, 0) / 1e6) AS min_ela_per_exec,
        MAX(elapsed_time / NULLIF(executions, 0) / 1e6) AS max_ela_per_exec
    FROM v$sql
    WHERE executions > 0
      AND plan_hash_value > 0
    GROUP BY sql_id
    HAVING COUNT(DISTINCT plan_hash_value) > 1
) p
  ON p.sql_id = q.sql_id
WHERE :run_vsql = 1
  AND q.executions > 0
  AND q.plan_hash_value > 0
GROUP BY
    q.sql_id,
    q.plan_hash_value,
    p.plan_count,
    p.min_ela_per_exec,
    p.max_ela_per_exec
ORDER BY p.plan_count DESC, q.sql_id, ela_per_exec DESC;

PROMPT
PROMPT === Unstable plans from AWR (requires Diagnostic Pack license) ===
PROMPT
PROMPT Querying DBA_HIST_SQLSTAT is a Diagnostic Pack feature. Pass VSQL to skip
PROMPT this section unless the database is licensed for that pack.
PROMPT

SET SERVEROUTPUT ON SIZE UNLIMITED

DECLARE
    TYPE t_row IS RECORD (
        sql_id              VARCHAR2(13),
        plan_hash_value     NUMBER,
        plan_count          NUMBER,
        executions          NUMBER,
        elapsed_sec         NUMBER,
        ela_per_exec        NUMBER,
        gets_per_exec       NUMBER,
        min_ela_per_exec    NUMBER,
        max_ela_per_exec    NUMBER,
        parsing_schema_name VARCHAR2(128),
        sql_text            VARCHAR2(50)
    );
    TYPE t_tab IS TABLE OF t_row;
    l_rows t_tab;
    l_sql  VARCHAR2(32767);
    l_days NUMBER := :lookback;
BEGIN
    IF :run_awr = 0 THEN
        DBMS_OUTPUT.PUT_LINE(
            'AWR section skipped. Pass AWR or ALL to query DBA_HIST_* (Diagnostic Pack).'
        );
        RETURN;
    END IF;

    DBMS_OUTPUT.PUT_LINE('Lookback: ' || l_days || ' days.');
    DBMS_OUTPUT.PUT_LINE(
        RPAD('SQL ID', 13) || ' ' ||
        LPAD('Plan Hash', 10) || ' ' ||
        LPAD('Plans', 5) || ' ' ||
        LPAD('Execs', 12) || ' ' ||
        LPAD('Elapsed S', 12) || ' ' ||
        LPAD('Ela/Exec', 10) || ' ' ||
        LPAD('Gets/Exec', 12) || ' ' ||
        LPAD('Min Ela', 10) || ' ' ||
        LPAD('Max Ela', 10) || ' ' ||
        RPAD('Schema', 20) || ' ' ||
        'SQL Text'
    );

    l_sql :=
        'SELECT h.sql_id,'
        || ' h.plan_hash_value,'
        || ' p.plan_count,'
        || ' SUM(h.executions_delta),'
        || ' ROUND(SUM(h.elapsed_time_delta) / 1e6, 3),'
        || ' ROUND(SUM(h.elapsed_time_delta) / NULLIF(SUM(h.executions_delta), 0) / 1e6, 4),'
        || ' ROUND(SUM(h.buffer_gets_delta) / NULLIF(SUM(h.executions_delta), 0), 0),'
        || ' ROUND(p.min_ela_per_exec, 4),'
        || ' ROUND(p.max_ela_per_exec, 4),'
        || ' MIN(h.parsing_schema_name),'
        || ' MIN(DBMS_LOB.SUBSTR(t.sql_text, 50, 1))'
        || ' FROM dba_hist_sqlstat h'
        || ' JOIN dba_hist_snapshot snap'
        || '   ON snap.snap_id = h.snap_id'
        || '  AND snap.dbid = h.dbid'
        || '  AND snap.instance_number = h.instance_number'
        || ' JOIN ('
        || '     SELECT hs.sql_id,'
        || '            COUNT(DISTINCT hs.plan_hash_value) AS plan_count,'
        || '            MIN(hs.elapsed_time_delta / NULLIF(hs.executions_delta, 0) / 1e6) AS min_ela_per_exec,'
        || '            MAX(hs.elapsed_time_delta / NULLIF(hs.executions_delta, 0) / 1e6) AS max_ela_per_exec'
        || '     FROM dba_hist_sqlstat hs'
        || '     JOIN dba_hist_snapshot sn'
        || '       ON sn.snap_id = hs.snap_id'
        || '      AND sn.dbid = hs.dbid'
        || '      AND sn.instance_number = hs.instance_number'
        || '     WHERE sn.begin_interval_time >= SYSDATE - :days'
        || '       AND hs.executions_delta > 0'
        || '       AND hs.plan_hash_value > 0'
        || '     GROUP BY hs.sql_id'
        || '     HAVING COUNT(DISTINCT hs.plan_hash_value) > 1'
        || ' ) p ON p.sql_id = h.sql_id'
        || ' LEFT JOIN dba_hist_sqltext t'
        || '   ON t.sql_id = h.sql_id'
        || '  AND t.dbid = h.dbid'
        || ' WHERE snap.begin_interval_time >= SYSDATE - :days'
        || '   AND h.executions_delta > 0'
        || '   AND h.plan_hash_value > 0'
        || ' GROUP BY h.sql_id, h.plan_hash_value, p.plan_count,'
        || '          p.min_ela_per_exec, p.max_ela_per_exec'
        || ' ORDER BY p.plan_count DESC, h.sql_id, 6 DESC';

    EXECUTE IMMEDIATE l_sql BULK COLLECT INTO l_rows USING l_days, l_days;

    IF l_rows.COUNT = 0 THEN
        DBMS_OUTPUT.PUT_LINE('No SQL with multiple AWR plans in the lookback window.');
        RETURN;
    END IF;

    FOR i IN 1 .. l_rows.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            RPAD(NVL(l_rows(i).sql_id, '-'), 13) || ' ' ||
            LPAD(TO_CHAR(l_rows(i).plan_hash_value), 10) || ' ' ||
            LPAD(TO_CHAR(l_rows(i).plan_count), 5) || ' ' ||
            LPAD(TO_CHAR(l_rows(i).executions, '999,999,999'), 12) || ' ' ||
            LPAD(TO_CHAR(l_rows(i).elapsed_sec, '9999990.000'), 12) || ' ' ||
            LPAD(TO_CHAR(l_rows(i).ela_per_exec, '9990.0000'), 10) || ' ' ||
            LPAD(TO_CHAR(l_rows(i).gets_per_exec, '999,999,999'), 12) || ' ' ||
            LPAD(TO_CHAR(l_rows(i).min_ela_per_exec, '9990.0000'), 10) || ' ' ||
            LPAD(TO_CHAR(l_rows(i).max_ela_per_exec, '9990.0000'), 10) || ' ' ||
            RPAD(NVL(l_rows(i).parsing_schema_name, '-'), 20) || ' ' ||
            REPLACE(REPLACE(NVL(l_rows(i).sql_text, ''), CHR(10), ' '), CHR(13), ' ')
        );
    END LOOP;
END;
/

COLUMN sql_id CLEAR
COLUMN plan_hash_value CLEAR
COLUMN plan_count CLEAR
COLUMN executions CLEAR
COLUMN elapsed_sec CLEAR
COLUMN ela_per_exec CLEAR
COLUMN gets_per_exec CLEAR
COLUMN min_ela_per_exec CLEAR
COLUMN max_ela_per_exec CLEAR
COLUMN parsing_schema_name CLEAR
COLUMN sql_text CLEAR

UNDEFINE p_source
UNDEFINE p_days
UNDEFINE 1
UNDEFINE 2
SET SERVEROUTPUT OFF
SET FEEDBACK ON
SET VERIFY ON
