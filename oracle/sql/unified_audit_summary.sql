/*******************************************************************************
*
* Script Name: unified_audit_summary.sql
* Title: Unified Audit Summary
* Tags: Security, Audit
* Purpose: Summarizes active Unified Auditing policies and recent security/audit events from audit_unified_enabled_policies and unified_audit_trail.
*
* Description:
*   Reports enabled Unified Auditing policies, audit configuration status,
*   and recent security and audit trail events from UNIFIED_AUDIT_TRAIL.
*   Includes summary breakdowns of audit actions, failed operations, and
*   recent security-sensitive database events.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on AUDIT_UNIFIED_ENABLED_POLICIES
*   - SELECT on UNIFIED_AUDIT_TRAIL
*   - SELECT on V$OPTION
*   - Or AUDIT_VIEWER, AUDIT_ADMIN, or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Unified Auditing feature status
*   - Enabled Unified Audit policies and target entities
*   - Audit events breakdown by action and return status (success / failure)
*   - Recent failed audit events (non-zero return code)
*   - Recent Unified Audit trail records
*
* Example Usage:
*   sqlplus user/password@yourdb @unified_audit_summary.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 200
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN parameter          FORMAT A30             HEADING 'Parameter'
COLUMN value              FORMAT A20             HEADING 'Value'
COLUMN policy_name        FORMAT A30             HEADING 'Policy Name'
COLUMN enabled_option     FORMAT A16             HEADING 'Enabled Option'
COLUMN entity_name        FORMAT A25             HEADING 'Entity Name'
COLUMN entity_type        FORMAT A15             HEADING 'Entity Type'
COLUMN success            FORMAT A8              HEADING 'Success'
COLUMN failure            FORMAT A8              HEADING 'Failure'
COLUMN action_name        FORMAT A28             HEADING 'Action Name'
COLUMN status             FORMAT A12             HEADING 'Status'
COLUMN event_count        FORMAT 999,999,990     HEADING 'Event Count'
COLUMN event_time         FORMAT A19             HEADING 'Event Timestamp'
COLUMN dbusername         FORMAT A20             HEADING 'DB User'
COLUMN return_code        FORMAT 999990          HEADING 'Ret Code'
COLUMN object_schema      FORMAT A18             HEADING 'Obj Schema'
COLUMN object_name        FORMAT A25             HEADING 'Object Name'
COLUMN client_program     FORMAT A25             HEADING 'Client Program'

PROMPT
PROMPT ===============================================================================
PROMPT Unified Audit Summary
PROMPT ===============================================================================

PROMPT
PROMPT === Unified Auditing Status ===
PROMPT

SELECT
    parameter,
    value
FROM v$option
WHERE parameter = 'Unified Auditing';

PROMPT
PROMPT === Enabled Unified Audit Policies ===
PROMPT

SELECT
    policy_name,
    enabled_option,
    entity_name,
    entity_type,
    success,
    failure
FROM audit_unified_enabled_policies
ORDER BY policy_name, entity_name;

PROMPT
PROMPT === Audit Events by Action & Status (Recent Summary) ===
PROMPT

SELECT
    action_name,
    CASE
        WHEN return_code = 0 THEN 'SUCCESS'
        ELSE 'FAILED (' || TO_CHAR(return_code) || ')'
    END AS status,
    COUNT(*) AS event_count
FROM (
    SELECT action_name, return_code
    FROM unified_audit_trail
    WHERE event_timestamp >= SYSTIMESTAMP - INTERVAL '7' DAY
)
GROUP BY
    action_name,
    CASE
        WHEN return_code = 0 THEN 'SUCCESS'
        ELSE 'FAILED (' || TO_CHAR(return_code) || ')'
    END
ORDER BY event_count DESC, action_name;

PROMPT
PROMPT === Recent Failed Audit Events ===
PROMPT

SELECT
    TO_CHAR(event_timestamp, 'YYYY-MM-DD HH24:MI:SS') AS event_time,
    dbusername,
    action_name,
    return_code,
    object_schema,
    object_name,
    SUBSTR(client_program_name, 1, 25) AS client_program
FROM (
    SELECT
        event_timestamp,
        dbusername,
        action_name,
        return_code,
        object_schema,
        object_name,
        client_program_name
    FROM unified_audit_trail
    WHERE return_code != 0
    ORDER BY event_timestamp DESC
)
WHERE ROWNUM <= 25;

PROMPT
PROMPT === Recent Unified Audit Trail Records ===
PROMPT

SELECT
    TO_CHAR(event_timestamp, 'YYYY-MM-DD HH24:MI:SS') AS event_time,
    dbusername,
    action_name,
    return_code,
    object_schema,
    object_name,
    SUBSTR(client_program_name, 1, 25) AS client_program
FROM (
    SELECT
        event_timestamp,
        dbusername,
        action_name,
        return_code,
        object_schema,
        object_name,
        client_program_name
    FROM unified_audit_trail
    ORDER BY event_timestamp DESC
)
WHERE ROWNUM <= 25;

COLUMN parameter CLEAR
COLUMN value CLEAR
COLUMN policy_name CLEAR
COLUMN enabled_option CLEAR
COLUMN entity_name CLEAR
COLUMN entity_type CLEAR
COLUMN success CLEAR
COLUMN failure CLEAR
COLUMN action_name CLEAR
COLUMN status CLEAR
COLUMN event_count CLEAR
COLUMN event_time CLEAR
COLUMN dbusername CLEAR
COLUMN return_code CLEAR
COLUMN object_schema CLEAR
COLUMN object_name CLEAR
COLUMN client_program CLEAR

SET FEEDBACK ON
SET VERIFY ON
