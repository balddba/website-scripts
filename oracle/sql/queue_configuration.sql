/*******************************************************************************
*
* Script Name: queue_configuration.sql
* Title: Queue Configuration
* Tags: AQ, Queues, Configuration
* Purpose: Display Oracle Advanced Queuing queue tables, queue definitions, subscribers, and propagation schedules
*
* Description:
*   Reports detailed configuration settings for Oracle Advanced Queuing (AQ)
*   objects. It displays queue table properties (payload types, sorting,
*   recipient settings), queue parameters (retention, retry delays, max retries,
*   enqueue/dequeue states), registered subscribers with rule conditions,
*   and propagation schedules. Accepts optional schema and queue name filters.
*
* Parameters:
*   &1 - (Optional) Schema/Owner name to filter. Default is all schemas (%).
*   &2 - (Optional) Queue name to filter. Default is all queues (%).
*
* Required Privileges:
*   - SELECT on DBA_QUEUE_TABLES
*   - SELECT on DBA_QUEUES
*   - SELECT on DBA_QUEUE_SUBSCRIBERS
*   - SELECT on DBA_QUEUE_SCHEDULES
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Queue Tables: Owner, table name, payload object type, sort order, recipients, grouping, compatibility, secure
*   - Queue Definitions: Owner, queue name, queue table, queue type, enqueue/dequeue status, max retries, retry delay, retention
*   - Queue Subscribers: Owner, queue name, consumer name, address, protocol, delivery mode, rule condition
*   - Propagation Schedules: Schema, queue name, destination, start time, latency, last run, next run, failures, disabled status
*
* Example Usage:
*   sqlplus / as sysdba @queue_configuration.sql
*   sqlplus / as sysdba @queue_configuration.sql SYSTEM
*   sqlplus / as sysdba @queue_configuration.sql SYSTEM DEF$_AQCALL
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET LINESIZE 240
SET PAGESIZE 100
SET VERIFY OFF
SET FEEDBACK OFF
SET TRIMSPOOL ON
SET TAB OFF
SET NULL '(null)'

COLUMN c_owner NEW_VALUE p_owner NOPRINT
COLUMN c_qname NEW_VALUE p_qname NOPRINT
SELECT
    NVL(CAST(UPPER(TRIM('&1')) AS VARCHAR2(128)), '%') AS c_owner,
    NVL(CAST(UPPER(TRIM('&2')) AS VARCHAR2(128)), '%') AS c_qname
FROM dual;

VARIABLE v_owner VARCHAR2(128)
VARIABLE v_qname VARCHAR2(128)

BEGIN
    IF '&&p_owner' = '%' THEN
        :v_owner := NULL;
    ELSE
        :v_owner := '&&p_owner';
    END IF;

    IF '&&p_qname' = '%' THEN
        :v_qname := NULL;
    ELSE
        :v_qname := '&&p_qname';
    END IF;
END;
/

COLUMN owner            FORMAT A18               HEADING 'Owner'
COLUMN queue_table      FORMAT A24               HEADING 'Queue Table'
COLUMN object_type      FORMAT A28               HEADING 'Payload Type'
COLUMN sort_order       FORMAT A18               HEADING 'Sort Order'
COLUMN recipients       FORMAT A10               HEADING 'Recipients'
COLUMN message_grouping FORMAT A14               HEADING 'Grouping'
COLUMN compatible       FORMAT A10               HEADING 'Compatible'
COLUMN secure           FORMAT A6                HEADING 'Secure'

COLUMN queue_name       FORMAT A26               HEADING 'Queue'
COLUMN queue_type       FORMAT A18               HEADING 'Queue Type'
COLUMN enqueue_enabled  FORMAT A8                HEADING 'Enqueue'
COLUMN dequeue_enabled  FORMAT A8                HEADING 'Dequeue'
COLUMN max_retries      FORMAT 9990              HEADING 'Retries'
COLUMN retry_delay      FORMAT 999,990           HEADING 'Retry Delay'
COLUMN retention        FORMAT A14               HEADING 'Retention'
COLUMN user_comment     FORMAT A30 TRUNC         HEADING 'Comment'

COLUMN consumer_name    FORMAT A24               HEADING 'Consumer'
COLUMN address          FORMAT A30 TRUNC         HEADING 'Address'
COLUMN protocol         FORMAT 9990              HEADING 'Protocol'
COLUMN delivery_mode    FORMAT A14               HEADING 'Delivery'
COLUMN rule             FORMAT A30 TRUNC         HEADING 'Rule Condition'

COLUMN schema           FORMAT A18               HEADING 'Owner'
COLUMN qname            FORMAT A24               HEADING 'Queue'
COLUMN destination      FORMAT A28 TRUNC         HEADING 'Destination'
COLUMN schedule_start   FORMAT A19               HEADING 'Start'
COLUMN latency          FORMAT 999,990           HEADING 'Latency'
COLUMN last_run         FORMAT A19               HEADING 'Last Run'
COLUMN next_run         FORMAT A19               HEADING 'Next Run'
COLUMN failures         FORMAT 9990              HEADING 'Failures'
COLUMN schedule_disabled FORMAT A8               HEADING 'Disabled'

PROMPT
PROMPT === Queue Tables Configuration ===
PROMPT

SELECT
    owner,
    queue_table,
    object_type,
    sort_order,
    recipients,
    message_grouping,
    compatible,
    secure
FROM dba_queue_tables
WHERE owner = NVL(:v_owner, owner)
ORDER BY owner, queue_table;

PROMPT
PROMPT === Queues Configuration ===
PROMPT

SELECT
    owner,
    name AS queue_name,
    queue_table,
    queue_type,
    enqueue_enabled,
    dequeue_enabled,
    max_retries,
    retry_delay,
    retention,
    user_comment
FROM dba_queues
WHERE owner = NVL(:v_owner, owner)
  AND name = NVL(:v_qname, name)
ORDER BY owner, name;

PROMPT
PROMPT === Queue Subscribers ===
PROMPT

SELECT
    s.owner,
    s.queue_name,
    s.consumer_name,
    s.address,
    s.protocol,
    s.delivery_mode,
    s.rule
FROM dba_queue_subscribers s
WHERE s.owner = NVL(:v_owner, s.owner)
  AND s.queue_name = NVL(:v_qname, s.queue_name)
ORDER BY s.owner, s.queue_name, s.consumer_name;

PROMPT
PROMPT === Queue Propagation Schedules ===
PROMPT

SELECT
    qs.schema,
    qs.qname,
    qs.destination,
    TO_CHAR(qs.start_date, 'YYYY-MM-DD HH24:MI:SS') AS schedule_start,
    qs.latency,
    TO_CHAR(qs.last_run_date, 'YYYY-MM-DD HH24:MI:SS') AS last_run,
    TO_CHAR(qs.next_run_date, 'YYYY-MM-DD HH24:MI:SS') AS next_run,
    qs.failures,
    qs.schedule_disabled
FROM dba_queue_schedules qs
WHERE qs.schema = NVL(:v_owner, qs.schema)
  AND qs.qname = NVL(:v_qname, qs.qname)
ORDER BY qs.schema, qs.qname, qs.destination;

COLUMN owner CLEAR
COLUMN queue_table CLEAR
COLUMN object_type CLEAR
COLUMN sort_order CLEAR
COLUMN recipients CLEAR
COLUMN message_grouping CLEAR
COLUMN compatible CLEAR
COLUMN secure CLEAR
COLUMN queue_name CLEAR
COLUMN queue_type CLEAR
COLUMN enqueue_enabled CLEAR
COLUMN dequeue_enabled CLEAR
COLUMN max_retries CLEAR
COLUMN retry_delay CLEAR
COLUMN retention CLEAR
COLUMN user_comment CLEAR
COLUMN consumer_name CLEAR
COLUMN address CLEAR
COLUMN protocol CLEAR
COLUMN delivery_mode CLEAR
COLUMN rule CLEAR
COLUMN schema CLEAR
COLUMN qname CLEAR
COLUMN destination CLEAR
COLUMN schedule_start CLEAR
COLUMN latency CLEAR
COLUMN last_run CLEAR
COLUMN next_run CLEAR
COLUMN failures CLEAR
COLUMN schedule_disabled CLEAR
COLUMN c_owner CLEAR
COLUMN c_qname CLEAR

SET NULL ''
SET FEEDBACK ON
SET VERIFY ON
