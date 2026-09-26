-- ============================================================================
-- Script: seqfix.sql
-- Description: Synchronizes an Oracle sequence with the maximum value of a
--              specified table column, ensuring the next sequence value
--              generated is strictly greater than the maximum column value.
--
-- Usage in SQL*Plus / SQLcl:
--   @seqfix.sql <sequence_name> <table_name.column_name>
--   or:
--   @seqfix.sql <sequence_name> <table_name> <column_name>
--
-- Examples:
--   @seqfix.sql SCENES_SEQ SCENES.ID
--   @seqfix.sql STASH.SCENES_SEQ STASH.SCENES.ID
--   @seqfix.sql IMAGES_SEQ IMAGES ID
-- ============================================================================

SET SERVEROUTPUT ON SIZE UNLIMITED FORMAT WRAPPED
SET VERIFY OFF
SET FEEDBACK OFF

WHENEVER SQLERROR CONTINUE

DECLARE
    -- Inputs from SQL*Plus positional parameters
    p_raw_seq     VARCHAR2(128) := TRIM('&1');
    p_raw_target1 VARCHAR2(128) := TRIM('&2');
    p_raw_target2 VARCHAR2(128) := TRIM('&3');

    -- Parsed identifiers
    v_seq_owner   VARCHAR2(128);
    v_seq_name    VARCHAR2(128);
    v_tab_owner   VARCHAR2(128);
    v_tab_name    VARCHAR2(128);
    v_col_name    VARCHAR2(128);

    -- Sequence & Table stats
    v_orig_inc    NUMBER := 1;
    v_seq_count   NUMBER := 0;
    v_max_val     NUMBER := 0;
    v_curr_val    NUMBER := 0;
    v_adv_val     NUMBER := 0;
    v_diff        NUMBER := 0;
    v_next_val    NUMBER := 0;
    v_dot_pos1    NUMBER;
    v_dot_pos2    NUMBER;
    v_target_full VARCHAR2(256);
    v_sql         VARCHAR2(1000);
BEGIN
    DBMS_OUTPUT.PUT_LINE('--------------------------------------------------------------------------------');
    DBMS_OUTPUT.PUT_LINE('                    Oracle Sequence Synchronization Tool                        ');
    DBMS_OUTPUT.PUT_LINE('--------------------------------------------------------------------------------');

    -- Validate sequence parameter
    IF p_raw_seq IS NULL OR p_raw_seq = '&1' THEN
        DBMS_OUTPUT.PUT_LINE('ERROR: Sequence name parameter is required.');
        DBMS_OUTPUT.PUT_LINE('Usage: @seqfix.sql <sequence_name> <table_name.column_name>');
        RETURN;
    END IF;

    -- Validate target parameter
    IF p_raw_target1 IS NULL OR p_raw_target1 = '&2' THEN
        DBMS_OUTPUT.PUT_LINE('ERROR: Table.Column parameter is required.');
        DBMS_OUTPUT.PUT_LINE('Usage: @seqfix.sql <sequence_name> <table_name.column_name>');
        RETURN;
    END IF;

    -- Parse Sequence Name (optional OWNER.SEQUENCE_NAME)
    v_dot_pos1 := INSTR(p_raw_seq, '.');
    IF v_dot_pos1 > 0 THEN
        v_seq_owner := UPPER(SUBSTR(p_raw_seq, 1, v_dot_pos1 - 1));
        v_seq_name  := UPPER(SUBSTR(p_raw_seq, v_dot_pos1 + 1));
    ELSE
        v_seq_owner := USER;
        v_seq_name  := UPPER(p_raw_seq);
    END IF;

    -- Parse Table and Column
    -- Check if target is split as param2 and param3, or combined with dot
    IF p_raw_target2 IS NOT NULL AND p_raw_target2 != '&3' THEN
        -- Case: @seqfix.sql SEQ TABLE COLUMN (or OWNER.TABLE COLUMN)
        v_col_name := UPPER(p_raw_target2);
        v_dot_pos1 := INSTR(p_raw_target1, '.');
        IF v_dot_pos1 > 0 THEN
            v_tab_owner := UPPER(SUBSTR(p_raw_target1, 1, v_dot_pos1 - 1));
            v_tab_name  := UPPER(SUBSTR(p_raw_target1, v_dot_pos1 + 1));
        ELSE
            v_tab_owner := USER;
            v_tab_name  := UPPER(p_raw_target1);
        END IF;
    ELSE
        -- Case: @seqfix.sql SEQ TABLE.COLUMN or SEQ OWNER.TABLE.COLUMN
        v_target_full := p_raw_target1;
        v_dot_pos1 := INSTR(v_target_full, '.');
        IF v_dot_pos1 = 0 THEN
            DBMS_OUTPUT.PUT_LINE('ERROR: Target column not specified. Format must be TABLE.COLUMN or OWNER.TABLE.COLUMN');
            RETURN;
        END IF;

        v_dot_pos2 := INSTR(v_target_full, '.', v_dot_pos1 + 1);
        IF v_dot_pos2 > 0 THEN
            -- OWNER.TABLE.COLUMN
            v_tab_owner := UPPER(SUBSTR(v_target_full, 1, v_dot_pos1 - 1));
            v_tab_name  := UPPER(SUBSTR(v_target_full, v_dot_pos1 + 1, v_dot_pos2 - v_dot_pos1 - 1));
            v_col_name  := UPPER(SUBSTR(v_target_full, v_dot_pos2 + 1));
        ELSE
            -- TABLE.COLUMN
            v_tab_owner := USER;
            v_tab_name  := UPPER(SUBSTR(v_target_full, 1, v_dot_pos1 - 1));
            v_col_name  := UPPER(SUBSTR(v_target_full, v_dot_pos1 + 1));
        END IF;
    END IF;

    DBMS_OUTPUT.PUT_LINE('Sequence : ' || v_seq_owner || '.' || v_seq_name);
    DBMS_OUTPUT.PUT_LINE('Target   : ' || v_tab_owner || '.' || v_tab_name || '.' || v_col_name);
    DBMS_OUTPUT.PUT_LINE('--------------------------------------------------------------------------------');

    -- Verify sequence existence and retrieve original INCREMENT_BY
    BEGIN
        SELECT increment_by
          INTO v_orig_inc
          FROM all_sequences
         WHERE sequence_owner = v_seq_owner
           AND sequence_name  = v_seq_name;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_OUTPUT.PUT_LINE('ERROR: Sequence ' || v_seq_owner || '.' || v_seq_name || ' not found in ALL_SEQUENCES.');
            RETURN;
    END;

    -- Query maximum value in the table column
    BEGIN
        v_sql := 'SELECT NVL(MAX(' || DBMS_ASSERT.ENQUOTE_NAME(v_col_name, FALSE) || '), 0) FROM '
              || DBMS_ASSERT.ENQUOTE_NAME(v_tab_owner, FALSE) || '.' || DBMS_ASSERT.ENQUOTE_NAME(v_tab_name, FALSE);
        EXECUTE IMMEDIATE v_sql INTO v_max_val;
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE('ERROR: Failed to query maximum value from ' || v_tab_owner || '.' || v_tab_name || '.' || v_col_name || ': ' || SQLERRM);
            RETURN;
    END;

    -- Retrieve current sequence value by advancing it once with its natural increment
    BEGIN
        v_sql := 'SELECT ' || DBMS_ASSERT.ENQUOTE_NAME(v_seq_owner, FALSE) || '.' || DBMS_ASSERT.ENQUOTE_NAME(v_seq_name, FALSE) || '.NEXTVAL FROM DUAL';
        EXECUTE IMMEDIATE v_sql INTO v_curr_val;
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE('ERROR: Failed to fetch NEXTVAL from sequence ' || v_seq_owner || '.' || v_seq_name || ': ' || SQLERRM);
            RETURN;
    END;

    DBMS_OUTPUT.PUT_LINE('Current Column MAX Value : ' || v_max_val);
    DBMS_OUTPUT.PUT_LINE('Sequence Current NEXTVAL : ' || v_curr_val);
    DBMS_OUTPUT.PUT_LINE('Original Increment       : ' || v_orig_inc);

    -- Check if sequence needs adjustment
    IF v_max_val <= v_curr_val THEN
        v_next_val := v_curr_val + v_orig_inc;
        DBMS_OUTPUT.PUT_LINE('Status                   : Sequence is already in sync.');
        DBMS_OUTPUT.PUT_LINE('Next generated value     : ' || v_next_val || ' (strictly > ' || v_max_val || ')');
        DBMS_OUTPUT.PUT_LINE('No modification required.');
        RETURN;
    END IF;

    -- Sequence is behind the table column max value; calculate difference
    v_diff := v_max_val - v_curr_val;
    DBMS_OUTPUT.PUT_LINE('Status                   : Sequence is BEHIND column max by ' || v_diff || ' values.');
    DBMS_OUTPUT.PUT_LINE('Advancing sequence to match table column...');

    BEGIN
        -- Step 1: Temporarily alter INCREMENT BY to jump the difference
        v_sql := 'ALTER SEQUENCE ' || DBMS_ASSERT.ENQUOTE_NAME(v_seq_owner, FALSE) || '.' || DBMS_ASSERT.ENQUOTE_NAME(v_seq_name, FALSE)
              || ' INCREMENT BY ' || v_diff;
        EXECUTE IMMEDIATE v_sql;

        -- Step 2: Advance sequence to equal v_max_val
        v_sql := 'SELECT ' || DBMS_ASSERT.ENQUOTE_NAME(v_seq_owner, FALSE) || '.' || DBMS_ASSERT.ENQUOTE_NAME(v_seq_name, FALSE) || '.NEXTVAL FROM DUAL';
        EXECUTE IMMEDIATE v_sql INTO v_adv_val;

        -- Step 3: Restore original INCREMENT BY
        v_sql := 'ALTER SEQUENCE ' || DBMS_ASSERT.ENQUOTE_NAME(v_seq_owner, FALSE) || '.' || DBMS_ASSERT.ENQUOTE_NAME(v_seq_name, FALSE)
              || ' INCREMENT BY ' || v_orig_inc;
        EXECUTE IMMEDIATE v_sql;

        v_next_val := v_adv_val + v_orig_inc;
        DBMS_OUTPUT.PUT_LINE('--------------------------------------------------------------------------------');
        DBMS_OUTPUT.PUT_LINE('SUCCESS: Sequence successfully synchronized!');
        DBMS_OUTPUT.PUT_LINE('  Last Sequence Value : ' || v_adv_val || ' (matches column max: ' || v_max_val || ')');
        DBMS_OUTPUT.PUT_LINE('  Next NEXTVAL Output : ' || v_next_val || ' (strictly > ' || v_max_val || ')');
        DBMS_OUTPUT.PUT_LINE('  Restored Increment  : ' || v_orig_inc);
        DBMS_OUTPUT.PUT_LINE('--------------------------------------------------------------------------------');
    EXCEPTION
        WHEN OTHERS THEN
            -- In case of failure during jump, attempt to restore original increment
            BEGIN
                EXECUTE IMMEDIATE 'ALTER SEQUENCE ' || DBMS_ASSERT.ENQUOTE_NAME(v_seq_owner, FALSE) || '.' || DBMS_ASSERT.ENQUOTE_NAME(v_seq_name, FALSE)
                               || ' INCREMENT BY ' || v_orig_inc;
            EXCEPTION
                WHEN OTHERS THEN
                    NULL;
            END;
            DBMS_OUTPUT.PUT_LINE('ERROR during sequence adjustment: ' || SQLERRM);
    END;
END;
/
