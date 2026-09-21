/*******************************************************************************
*
* Script Name: aq.sql
* Title: Advanced Queuing overview
* Tags: AQ, Queues
* Purpose: Inventory AQ queue tables, queues, message counts, and enqueue/dequeue activity
*
* Description:
*   Lists DBA_QUEUE_TABLES and DBA_QUEUES, then joins V$AQ for waiting, ready,
*   and expired message counts. GV$PERSISTENT_QUEUES adds lifetime enqueue and
*   dequeue counts when that view is present (12c and later). Pass a schema
*   to limit the report. Press Enter at the SQL*Plus prompt if no argument is
*   passed.
*
* Parameters:
*   &1 - (Optional) Schema owner. Default is all schemas.
*
* Required Privileges:
*   - SELECT on DBA_QUEUE_TABLES
*   - SELECT on DBA_QUEUES
*   - SELECT on V$AQ
*   - SELECT on GV$PERSISTENT_QUEUES
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Queue tables: type, payload, sort order, and recipients
*   - Queues: type, table, enqueue/dequeue enabled, retries, and retention
*   - V$AQ waiting, ready, expired, and average wait
*   - Persistent-queue enqueue and dequeue counts per instance
*
* Example Usage:
*   SQL> @aq.sql
*   SQL> @aq.sql HR
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 240
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF
SET NULL '(null)'

-- Optional &1: SQL*Plus prompts if omitted; Enter (empty) means every schema.
COLUMN c_owner NEW_VALUE p_owner NOPRINT
SELECT NVL(CAST(UPPER(TRIM('&1')) AS VARCHAR2(128)), '%') AS c_owner FROM dual;

VARIABLE schema_filter VARCHAR2(128)

BEGIN
    IF '&&p_owner' = '%' THEN
        :schema_filter := NULL;
    ELSE
        :schema_filter := '&&p_owner';
    END IF;
END;
/

COLUMN owner            FORMAT A20               HEADING 'Owner'
COLUMN queue_table      FORMAT A30               HEADING 'Queue Table'
COLUMN object_type      FORMAT A32               HEADING 'Payload Type'
COLUMN sort_order       FORMAT A24               HEADING 'Sort Order'
COLUMN recipients       FORMAT A10               HEADING 'Recipients'
COLUMN message_grouping FORMAT A16               HEADING 'Grouping'
COLUMN compatible       FORMAT A10               HEADING 'Compatible'
COLUMN secure           FORMAT A6                HEADING 'Secure'
COLUMN queue_name       FORMAT A30               HEADING 'Queue'
COLUMN queue_type       FORMAT A20               HEADING 'Queue Type'
COLUMN qid              FORMAT 9999999999        HEADING 'QID'
COLUMN enqueue_enabled  FORMAT A8                HEADING 'Enqueue'
COLUMN dequeue_enabled  FORMAT A8                HEADING 'Dequeue'
COLUMN max_retries      FORMAT 9990              HEADING 'Retries'
COLUMN retry_delay      FORMAT 999,990           HEADING 'Retry Delay'
COLUMN retention        FORMAT A16               HEADING 'Retention'
COLUMN user_comment     FORMAT A40 TRUNC         HEADING 'Comment'
COLUMN waiting          FORMAT 999,999,990       HEADING 'Waiting'
COLUMN ready            FORMAT 999,999,990       HEADING 'Ready'
COLUMN expired          FORMAT 999,999,990       HEADING 'Expired'
COLUMN total_wait       FORMAT 999,999,990       HEADING 'Total Wait'
COLUMN average_wait     FORMAT 999,990.00        HEADING 'Avg Wait'
COLUMN inst_id          FORMAT 999               HEADING 'Inst'
COLUMN enqueued_msgs    FORMAT 999,999,999,990   HEADING 'Enqueued'
COLUMN dequeued_msgs    FORMAT 999,999,999,990   HEADING 'Dequeued'
COLUMN browsed_msgs     FORMAT 999,999,999,990   HEADING 'Browsed'
COLUMN avg_msg_age      FORMAT 999,999,990       HEADING 'Avg Age'
COLUMN first_activity   FORMAT A19               HEADING 'First Activity'
COLUMN elapsed_enq      FORMAT 999,999,999,990   HEADING 'Enq Time'
COLUMN elapsed_deq      FORMAT 999,999,999,990   HEADING 'Deq Time'

PROMPT
PROMPT === Queue tables ===
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
WHERE owner = NVL(:schema_filter, owner)
ORDER BY owner, queue_table;

PROMPT
PROMPT === Queues ===
PROMPT

SELECT
    owner,
    name AS queue_name,
    queue_table,
    queue_type,
    qid,
    enqueue_enabled,
    dequeue_enabled,
    max_retries,
    retry_delay,
    retention,
    user_comment
FROM dba_queues
WHERE owner = NVL(:schema_filter, owner)
ORDER BY owner, name;

PROMPT
PROMPT === Message counts (V$AQ) ===
PROMPT

SELECT
    q.owner,
    q.name AS queue_name,
    q.queue_table,
    aq.waiting,
    aq.ready,
    aq.expired,
    aq.total_wait,
    aq.average_wait
FROM dba_queues q
JOIN v$aq aq
  ON aq.qid = q.qid
WHERE q.owner = NVL(:schema_filter, owner)
ORDER BY
    aq.ready DESC,
    aq.waiting DESC,
    q.owner,
    q.name;

PROMPT
PROMPT === Persistent queue stats (GV$PERSISTENT_QUEUES) ===
PROMPT
PROMPT Enq/Deq Time are hundredths of a second spent in enqueue and dequeue.
PROMPT

SELECT
    pq.inst_id,
    q.owner,
    q.name AS queue_name,
    q.queue_table,
    pq.enqueued_msgs,
    pq.dequeued_msgs,
    pq.browsed_msgs,
    pq.avg_msg_age,
    pq.elapsed_enqueue_time AS elapsed_enq,
    pq.elapsed_dequeue_time AS elapsed_deq,
    TO_CHAR(pq.first_activity_time, 'YYYY-MM-DD HH24:MI:SS') AS first_activity
FROM gv$persistent_queues pq
JOIN dba_queues q
  ON q.qid = pq.queue_id
 AND q.owner = pq.queue_schema
WHERE q.owner = NVL(:schema_filter, owner)
ORDER BY
    pq.enqueued_msgs DESC,
    q.owner,
    q.name,
    pq.inst_id;

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
COLUMN qid CLEAR
COLUMN enqueue_enabled CLEAR
COLUMN dequeue_enabled CLEAR
COLUMN max_retries CLEAR
COLUMN retry_delay CLEAR
COLUMN retention CLEAR
COLUMN user_comment CLEAR
COLUMN waiting CLEAR
COLUMN ready CLEAR
COLUMN expired CLEAR
COLUMN total_wait CLEAR
COLUMN average_wait CLEAR
COLUMN inst_id CLEAR
COLUMN enqueued_msgs CLEAR
COLUMN dequeued_msgs CLEAR
COLUMN browsed_msgs CLEAR
COLUMN avg_msg_age CLEAR
COLUMN first_activity CLEAR
COLUMN elapsed_enq CLEAR
COLUMN elapsed_deq CLEAR
COLUMN c_owner CLEAR

SET NULL ''
SET FEEDBACK ON
SET VERIFY ON
