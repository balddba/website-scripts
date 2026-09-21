/*******************************************************************************
*
* Script Name: database_links.sql
* Title: Database links
* Tags: Database Links, Network
* Purpose: List database links from DBA_DB_LINKS (owner, name, username, host, created)
*
* Description:
*   Reports every database link visible in DBA_DB_LINKS. USERNAME is the
*   remote account stored on the link; HOST is the connect string. Passwords
*   are not selected. Older dictionaries stored a PASSWORD column that is
*   unused; this script never reads SYS.LINK$ or any password verifier.
*   Press Enter at the SQL*Plus prompt if the optional owner is omitted.
*
* Parameters:
*   &1 - (Optional) Link owner. If omitted, every owner is listed
*
* Required Privileges:
*   - SELECT on DBA_DB_LINKS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Owner, database link name, remote username, host, and created date
*
* Example Usage:
*   SQL> @database_links.sql
*   SQL> @database_links.sql SCOTT
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

COLUMN owner     FORMAT A30              HEADING 'Owner'
COLUMN db_link   FORMAT A40              HEADING 'DB Link'
COLUMN username  FORMAT A30              HEADING 'Remote User'
COLUMN host      FORMAT A60 TRUNC        HEADING 'Host'
COLUMN created   FORMAT A19              HEADING 'Created'

PROMPT
PROMPT === Database links ===
PROMPT
PROMPT Passwords are not displayed.

SELECT
    owner,
    db_link,
    username,
    host,
    TO_CHAR(created, 'YYYY-MM-DD HH24:MI:SS') AS created
FROM dba_db_links
WHERE CAST(owner AS VARCHAR2(128)) = NVL(
    CAST(UPPER(TRIM('&1')) AS VARCHAR2(128)),
    CAST(owner AS VARCHAR2(128))
)
ORDER BY owner, db_link;

COLUMN owner CLEAR
COLUMN db_link CLEAR
COLUMN username CLEAR
COLUMN host CLEAR
COLUMN created CLEAR

SET FEEDBACK ON
SET VERIFY ON
