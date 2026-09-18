/*******************************************************************************
*
* Script Name: autoextend_report.sql
* Title: Autoextend report
* Tags: Capacity, Datafiles
* Purpose: Reports auto-extend settings for Oracle tablespaces and their datafiles
*
* Description:
*   This script generates a formatted report showing the auto-extend settings
*   for Oracle database datafiles. It can report on either all tablespaces
*   or a specific tablespace if provided as an argument.
*
* Parameters:
*   &1 - (Optional) Tablespace name to filter results
*        If not provided, script will report on all tablespaces
*
* Required Privileges:
*   - SELECT on DBA_DATA_FILES
*
* Output Format:
*   For each tablespace:
*   - Tablespace name
*   - File name (60 chars)
*   - Size in MB
*   - Auto-extend setting (TRUE/FALSE)
*
* Example Usage:
*   @autoextend_report         -- Report on all tablespaces
*   @autoextend_report USERS   -- Report on USERS tablespace only
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/
SET SERVEROUTPUT ON
SET VERIFY OFF

-- Accept optional tablespace name parameter
DEFINE ts_name = '&1'

DECLARE
    v_filter_ts     VARCHAR2(30) := TRIM(UPPER('&&ts_name'));
    v_current_ts    VARCHAR2(30) := '';
    v_filename_width CONSTANT PLS_INTEGER := 60;
    v_ts_width       CONSTANT PLS_INTEGER := 20;

    CURSOR all_datafiles IS
        SELECT tablespace_name,
               file_name,
               autoextensible,
               bytes / 1024 / 1024 AS size_mb
        FROM dba_data_files
        ORDER BY tablespace_name, file_name;

    CURSOR filtered_datafiles(p_ts VARCHAR2) IS
        SELECT tablespace_name,
               file_name,
               autoextensible,
               bytes / 1024 / 1024 AS size_mb
        FROM dba_data_files
        WHERE UPPER(tablespace_name) = p_ts
        ORDER BY tablespace_name, file_name;

    PROCEDURE print_header IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(RPAD('TABLESPACE', v_ts_width) || ' | ' ||
                             RPAD('FILE NAME', v_filename_width) || ' | ' ||
                             RPAD('SIZE (MB)', 10) || ' | ' ||
                             'AUTOEXTEND');
        DBMS_OUTPUT.PUT_LINE(RPAD('-', v_ts_width, '-') || '-|-' ||
                             RPAD('-', v_filename_width, '-') || '-|-' ||
                             RPAD('-', 10, '-') || '-|-' ||
                             RPAD('-', 11, '-'));
    END;

BEGIN
    IF NVL(v_filter_ts, 'NULL') = 'NULL' THEN
        DBMS_OUTPUT.PUT_LINE('Checking auto-extend settings for ALL tablespaces...');
        DBMS_OUTPUT.PUT_LINE(RPAD('-', v_ts_width + v_filename_width + 27, '-'));
        print_header;

        FOR df IN all_datafiles LOOP
            DBMS_OUTPUT.PUT_LINE(
                RPAD(df.tablespace_name, v_ts_width) || ' | ' ||
                RPAD(df.file_name, v_filename_width) || ' | ' ||
                LPAD(TO_CHAR(ROUND(df.size_mb, 2)), 10) || ' | ' ||
                RPAD(df.autoextensible, 11)
            );
        END LOOP;

    ELSE
        DBMS_OUTPUT.PUT_LINE('Checking auto-extend settings for tablespace: ' || v_filter_ts);
        DBMS_OUTPUT.PUT_LINE(RPAD('-', v_ts_width + v_filename_width + 27, '-'));
        print_header;

        FOR df IN filtered_datafiles(v_filter_ts) LOOP
            DBMS_OUTPUT.PUT_LINE(
                RPAD(df.tablespace_name, v_ts_width) || ' | ' ||
                RPAD(df.file_name, v_filename_width) || ' | ' ||
                LPAD(TO_CHAR(ROUND(df.size_mb, 2)), 10) || ' | ' ||
                RPAD(df.autoextensible, 11)
            );
        END LOOP;
    END IF;
END;
/

-- Cleanup
UNDEFINE ts_name