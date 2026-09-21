/*******************************************************************************
*
* Script Name: installed_options.sql
* Title: Installed database options
* Tags: Licensing, Options
* Purpose: List every Oracle Database option from V$OPTION and whether it is installed
*
* Description:
*   Reports PARAMETER and VALUE from V$OPTION. Installed options (TRUE) are
*   listed first. This is the product-option inventory (Partitioning, RAC,
*   Advanced Compression, and so on), not DBA_REGISTRY components and not
*   DBA_FEATURE_USAGE_STATISTICS.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$OPTION
*   - SELECT on V$VERSION
*
* Output Format:
*   - Banner with database version
*   - Option name and installed flag (TRUE/FALSE)
*
* Example Usage:
*   SQL> @installed_options.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET LINESIZE 80
SET PAGESIZE 100
SET FEEDBACK OFF

COLUMN banner FORMAT A80 HEADING 'Database Version'

SELECT banner
FROM v$version
WHERE banner LIKE 'Oracle Database%'
  AND ROWNUM = 1;

SET FEEDBACK ON

COLUMN parameter FORMAT A55 HEADING 'Option'
COLUMN value     FORMAT A10 HEADING 'Installed'

SELECT
    parameter,
    value
FROM v$option
ORDER BY
    CASE WHEN value = 'TRUE' THEN 0 ELSE 1 END,
    parameter;
