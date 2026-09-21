/*******************************************************************************
*
* Script Name: sqlplus_prompt.sql
* Title: SQL*Plus username@dbname prompt
* Tags: SQLPlus, Session
* Purpose: Set the SQL*Plus prompt to username@dbname>
*
* Description:
*   Sets SQLPROMPT to USER@DBNAME> using the connected user and the
*   current container name when connected to a PDB, or DB_NAME in CDB$ROOT
*   and non-CDB databases. Run this from a login.sql or after CONNECT so
*   the prompt follows the session. SQL*Plus predefined _USER and
*   _CONNECT_IDENTIFIER are not used, so a TNS alias that differs from the
*   database name does not hide which container you are in.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - None beyond a connected SQL*Plus session (USERENV context)
*
* Output Format:
*   - No report. The SQL*Plus prompt becomes username@dbname>
*
* Example Usage:
*   SQL> @sqlplus_prompt.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET TERMOUT OFF

COLUMN sqlplus_user NEW_VALUE sqlplus_user NOPRINT
COLUMN sqlplus_db   NEW_VALUE sqlplus_db   NOPRINT

SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS sqlplus_user,
    NVL(
        NULLIF(SYS_CONTEXT('USERENV', 'CON_NAME'), 'CDB$ROOT'),
        SYS_CONTEXT('USERENV', 'DB_NAME')
    ) AS sqlplus_db
FROM dual;

SET TERMOUT ON
SET SQLPROMPT '&sqlplus_user.@&sqlplus_db.> '

COLUMN sqlplus_user CLEAR
COLUMN sqlplus_db CLEAR

SET FEEDBACK ON
SET VERIFY ON
