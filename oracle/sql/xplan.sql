/*******************************************************************************
*
* Script Name: xplan.sql
* Title: DBMS_XPLAN display
* Tags: SQL, Plans
* Purpose: Print the current explained plan from DBMS_XPLAN.DISPLAY
*
* Description:
*   Thin wrapper that selects from TABLE(DBMS_XPLAN.DISPLAY) after EXPLAIN PLAN.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on PLAN_TABLE
*   - Execute DBMS_XPLAN
*
* Output Format:
*   - DBMS_XPLAN formatted execution plan
*
* Example Usage:
*   EXPLAIN PLAN FOR SELECT * FROM dual;
*   @xplan.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/
SET LINESIZE 130
SET PAGESIZE 0
SELECT * 
FROM   TABLE(DBMS_XPLAN.DISPLAY);
