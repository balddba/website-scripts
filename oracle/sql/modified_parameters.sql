/*******************************************************************************
*
* Script Name: modified_parameters.sql
* Title: Modified instance parameters
* Tags: Parameters, Hidden, Instance
* Purpose: Show documented and hidden (_underscore) parameters that differ from default
*
* Description:
*   Lists every parameter whose current value is not the default
*   (isdefault = FALSE), including hidden names that start with an
*   underscore. The first report uses V$PARAMETER and works with
*   SELECT_CATALOG_ROLE (non-hidden only). The second report joins
*   X$KSPPI and X$KSPPCV so hidden parameters appear; that query must
*   run as SYS or a user connected AS SYSDBA. If the X$ query fails with
*   ORA-00942, the V$PARAMETER section above is still valid. This is a
*   standard catalog diagnostic, not an exploit.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$PARAMETER (non-hidden modified values)
*   - SYS / SYSDBA to read X$KSPPI and X$KSPPCV (hidden parameters)
*
* Output Format:
*   - Non-hidden modified parameters from V$PARAMETER
*   - All modified parameters including hidden names from X$KSPPI / X$KSPPCV
*   - Name, value, display_value, isdefault, issys_modifiable, description
*
* Example Usage:
*   SQL> CONNECT / AS SYSDBA
*   SQL> @modified_parameters.sql
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

COLUMN name                    FORMAT A50              HEADING 'Name'
COLUMN value                   FORMAT A40 TRUNC        HEADING 'Value'
COLUMN display_value           FORMAT A40 TRUNC        HEADING 'Display'
COLUMN isdefault               FORMAT A9               HEADING 'Default'
COLUMN issys_modifiable        FORMAT A12              HEADING 'Sys Mod'
COLUMN isinstance_modifiable   FORMAT A10              HEADING 'Inst Mod'
COLUMN hidden_param            FORMAT A7               HEADING 'Hidden'
COLUMN description             FORMAT A70 TRUNC        HEADING 'Description'

PROMPT
PROMPT === Modified parameters (V$PARAMETER, non-hidden) ===
PROMPT
PROMPT isdefault = FALSE. Hidden names are not in this view.

SELECT
    name,
    value,
    display_value,
    isdefault,
    issys_modifiable,
    isinstance_modifiable,
    description
FROM v$parameter
WHERE isdefault = 'FALSE'
  AND name NOT LIKE '\_%' ESCAPE '\'
ORDER BY name;

PROMPT
PROMPT === Modified parameters including hidden (X$KSPPI / X$KSPPCV) ===
PROMPT
PROMPT Requires SYS or SYSDBA. If this query fails (ORA-00942), reconnect
PROMPT AS SYSDBA. Names that start with _ are hidden underscore parameters.

SELECT
    i.ksppinm AS name,
    c.ksppstvl AS value,
    c.ksppstvl AS display_value,
    c.ksppstdf AS isdefault,
    DECODE(
        BITAND(i.ksppiflg / 65536, 3),
        1, 'IMMEDIATE',
        2, 'DEFERRED',
        3, 'IMMEDIATE',
        'FALSE'
    ) AS issys_modifiable,
    CASE
        WHEN i.ksppinm LIKE '\_%' ESCAPE '\' THEN 'TRUE'
        ELSE 'FALSE'
    END AS hidden_param,
    i.ksppdesc AS description
FROM x$ksppi i
JOIN x$ksppcv c
    ON c.indx = i.indx
WHERE c.ksppstdf = 'FALSE'
ORDER BY i.ksppinm;

COLUMN name CLEAR
COLUMN value CLEAR
COLUMN display_value CLEAR
COLUMN isdefault CLEAR
COLUMN issys_modifiable CLEAR
COLUMN isinstance_modifiable CLEAR
COLUMN hidden_param CLEAR
COLUMN description CLEAR

SET FEEDBACK ON
SET VERIFY ON
