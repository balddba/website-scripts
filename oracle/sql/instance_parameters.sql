/*******************************************************************************
*
* Script Name: instance_parameters.sql
* Title: Instance parameters
* Tags: Parameters, Instance
* Purpose: Display non-hidden instance parameters from V$PARAMETER
*
* Description:
*   Lists documented (non-underscore) parameters from V$PARAMETER: name,
*   value, display_value, isdefault, issys_modifiable, isinstance_modifiable,
*   and description. Hidden (_underscore) parameters are omitted; use
*   modified_parameters.sql for those. Press Enter at the SQL*Plus prompt
*   if the optional name pattern is omitted. The pattern is a SQL LIKE
*   expression against the lowercase parameter name (for example cpu% or
*   %pool%).
*
* Parameters:
*   &1 - (Optional) Parameter name LIKE pattern. Default: all non-hidden
*
* Required Privileges:
*   - SELECT on V$PARAMETER
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Name, value, display_value, isdefault
*   - issys_modifiable, isinstance_modifiable, description
*
* Example Usage:
*   SQL> @instance_parameters.sql
*   SQL> @instance_parameters.sql cpu%
*   SQL> @instance_parameters.sql %archive%
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 260
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF
SET WRAP ON

COLUMN name                    FORMAT A40              HEADING 'Name'
COLUMN value                   FORMAT A40 TRUNC        HEADING 'Value'
COLUMN display_value           FORMAT A40 TRUNC        HEADING 'Display'
COLUMN isdefault               FORMAT A9               HEADING 'Default'
COLUMN issys_modifiable        FORMAT A12              HEADING 'Sys Mod'
COLUMN isinstance_modifiable   FORMAT A10              HEADING 'Inst Mod'
COLUMN description             FORMAT A70 TRUNC        HEADING 'Description'

PROMPT
PROMPT === Instance parameters (non-hidden) ===
PROMPT

SELECT
    name,
    value,
    display_value,
    isdefault,
    issys_modifiable,
    isinstance_modifiable,
    description
FROM v$parameter
WHERE name NOT LIKE '\_%' ESCAPE '\'
  AND name LIKE LOWER(NVL(CAST(TRIM('&1') AS VARCHAR2(128)), '%'))
ORDER BY name;

COLUMN name CLEAR
COLUMN value CLEAR
COLUMN display_value CLEAR
COLUMN isdefault CLEAR
COLUMN issys_modifiable CLEAR
COLUMN isinstance_modifiable CLEAR
COLUMN description CLEAR

SET FEEDBACK ON
SET VERIFY ON
