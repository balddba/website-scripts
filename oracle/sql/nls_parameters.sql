/*******************************************************************************
*
* Script Name: nls_parameters.sql
* Title: NLS parameters
* Tags: NLS, Parameters
* Purpose: Show session, instance, and database NLS parameters
*
* Description:
*   Prints NLS_SESSION_PARAMETERS, NLS_INSTANCE_PARAMETERS, and
*   NLS_DATABASE_PARAMETERS as three labeled reports. Session values follow
*   the client and ALTER SESSION. Instance values come from the instance
*   initialization parameters. Database values are stored in the data
*   dictionary (characterset, national characterset, and territory) and do
*   not change without recreating or migrating the database.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on NLS_SESSION_PARAMETERS
*   - SELECT on NLS_INSTANCE_PARAMETERS
*   - SELECT on NLS_DATABASE_PARAMETERS
*
* Output Format:
*   - Parameter name and value for session, instance, and database scopes
*
* Example Usage:
*   SQL> @nls_parameters.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 120
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN parameter FORMAT A40              HEADING 'Parameter'
COLUMN value     FORMAT A60              HEADING 'Value'

PROMPT
PROMPT === Session NLS parameters ===
PROMPT

SELECT parameter, value
FROM nls_session_parameters
ORDER BY parameter;

PROMPT
PROMPT === Instance NLS parameters ===
PROMPT

SELECT parameter, value
FROM nls_instance_parameters
ORDER BY parameter;

PROMPT
PROMPT === Database NLS parameters ===
PROMPT

SELECT parameter, value
FROM nls_database_parameters
ORDER BY parameter;

COLUMN parameter CLEAR
COLUMN value CLEAR

SET FEEDBACK ON
SET VERIFY ON
