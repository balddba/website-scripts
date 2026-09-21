/*******************************************************************************
*
* Script Name: aq_queue.sql
* Title: Advanced Queuing queue detail
* Tags: AQ, Queues
* Purpose: Show definition, subscribers, schedules, and message counts for one AQ queue
*
* Description:
*   Resolves one queue from DBA_QUEUES and its DBA_QUEUE_TABLES row, then lists
*   DBA_QUEUE_SUBSCRIBERS and DBA_QUEUE_SCHEDULES (propagation) when present.
*   V$AQ supplies waiting, ready, and expired counts; GV$PERSISTENT_QUEUES
*   adds enqueue and dequeue totals per instance. Accepts OWNER.QUEUE_NAME
*   or OWNER plus QUEUE_NAME. Press Enter at the SQL*Plus prompt if the
*   second argument is omitted.
*
* Parameters:
*   &1 - Required queue: OWNER.QUEUE_NAME, or owner when &2 is the queue name
*   &2 - Queue name when &1 is owner only
*
* Required Privileges:
*   - SELECT on DBA_QUEUES
*   - SELECT on DBA_QUEUE_TABLES
*   - SELECT on DBA_QUEUE_SUBSCRIBERS
*   - SELECT on DBA_QUEUE_SCHEDULES
*   - SELECT on V$AQ
*   - SELECT on GV$PERSISTENT_QUEUES
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Queue identity, type, enable flags, retries, and retention
*   - Queue table payload type, sort order, and recipients
*   - Subscribers and propagation schedules
*   - V$AQ message counts and persistent-queue enqueue/dequeue stats
*
* Example Usage:
*   SQL> @aq_queue.sql SYS.ALERT_QUE
*   SQL> @aq_queue.sql HR ORDER_QUEUE
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

COLUMN c_arg1 NEW_VALUE p_arg1 NOPRINT
COLUMN c_arg2 NEW_VALUE p_arg2 NOPRINT
SELECT TRIM('&1') AS c_arg1, TRIM('&2') AS c_arg2 FROM dual;

VARIABLE queue_owner VARCHAR2(128)
VARIABLE queue_name  VARCHAR2(128)

DECLARE
    l_a1  VARCHAR2(261) := UPPER(TRIM('&&p_arg1'));
    l_a2  VARCHAR2(128) := NULLIF(UPPER(TRIM('&&p_arg2')), '');
    l_dot PLS_INTEGER;
    l_cnt PLS_INTEGER;
BEGIN
    IF l_a1 IS NULL THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Queue must be OWNER.QUEUE_NAME or OWNER QUEUE_NAME.'
        );
    END IF;

    l_dot := INSTR(l_a1, '.');
    IF l_dot > 0 THEN
        IF l_dot = 1
           OR l_dot = LENGTH(l_a1)
           OR INSTR(l_a1, '.', l_dot + 1) > 0 THEN
            RAISE_APPLICATION_ERROR(
                -20001,
                'Queue must be OWNER.QUEUE_NAME or OWNER QUEUE_NAME.'
            );
        END IF;
        :queue_owner := SUBSTR(l_a1, 1, l_dot - 1);
        :queue_name  := SUBSTR(l_a1, l_dot + 1);
    ELSIF l_a2 IS NOT NULL THEN
        :queue_owner := l_a1;
        :queue_name  := l_a2;
    ELSE
        RAISE_APPLICATION_ERROR(
            -20001,
            'Queue must be OWNER.QUEUE_NAME or OWNER QUEUE_NAME.'
        );
    END IF;

    SELECT COUNT(*)
    INTO l_cnt
    FROM dba_queues
    WHERE owner = :queue_owner
      AND name = :queue_name;

    IF l_cnt = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Queue ' || :queue_owner || '.' || :queue_name
                || ' was not found in DBA_QUEUES.'
        );
    END IF;
END;
/

COLUMN owner            FORMAT A20               HEADING 'Owner'
COLUMN queue_name       FORMAT A30               HEADING 'Queue'
COLUMN queue_table      FORMAT A30               HEADING 'Queue Table'
COLUMN queue_type       FORMAT A20               HEADING 'Queue Type'
COLUMN qid              FORMAT 9999999999        HEADING 'QID'
COLUMN enqueue_enabled  FORMAT A8                HEADING 'Enqueue'
COLUMN dequeue_enabled  FORMAT A8                HEADING 'Dequeue'
COLUMN max_retries      FORMAT 9990              HEADING 'Retries'
COLUMN retry_delay      FORMAT 999,990           HEADING 'Retry Delay'
COLUMN retention        FORMAT A16               HEADING 'Retention'
COLUMN user_comment     FORMAT A50 TRUNC         HEADING 'Comment'
COLUMN object_type      FORMAT A32               HEADING 'Payload Type'
COLUMN sort_order       FORMAT A24               HEADING 'Sort Order'
COLUMN recipients       FORMAT A10               HEADING 'Recipients'
COLUMN message_grouping FORMAT A16               HEADING 'Grouping'
COLUMN compatible       FORMAT A10               HEADING 'Compatible'
COLUMN secure           FORMAT A6                HEADING 'Secure'
COLUMN consumer_name    FORMAT A30               HEADING 'Consumer'
COLUMN address          FORMAT A50 TRUNC         HEADING 'Address'
COLUMN protocol         FORMAT 9990              HEADING 'Protocol'
COLUMN delivery_mode    FORMAT A16               HEADING 'Delivery'
COLUMN queue_to_queue   FORMAT A8                HEADING 'Q2Q'
COLUMN destination      FORMAT A40 TRUNC         HEADING 'Destination'
COLUMN schedule_start   FORMAT A19               HEADING 'Start'
COLUMN latency          FORMAT 999,990           HEADING 'Latency'
COLUMN last_run         FORMAT A19               HEADING 'Last Run'
COLUMN next_run         FORMAT A19               HEADING 'Next Run'
COLUMN failures         FORMAT 999,990           HEADING 'Failures'
COLUMN schedule_disabled FORMAT A8               HEADING 'Disabled'
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
PROMPT === Queue ===
PROMPT

SELECT
    q.owner,
    q.name AS queue_name,
    q.queue_table,
    q.queue_type,
    q.qid,
    q.enqueue_enabled,
    q.dequeue_enabled,
    q.max_retries,
    q.retry_delay,
    q.retention,
    q.user_comment
FROM dba_queues q
WHERE q.owner = :queue_owner
  AND q.name = :queue_name;

PROMPT
PROMPT === Queue table ===
PROMPT

SELECT
    qt.owner,
    qt.queue_table,
    qt.object_type,
    qt.sort_order,
    qt.recipients,
    qt.message_grouping,
    qt.compatible,
    qt.secure
FROM dba_queue_tables qt
JOIN dba_queues q
  ON q.owner = qt.owner
 AND q.queue_table = qt.queue_table
WHERE q.owner = :queue_owner
  AND q.name = :queue_name;

PROMPT
PROMPT === Subscribers ===
PROMPT

SELECT
    s.owner,
    s.queue_name,
    s.consumer_name,
    s.address,
    s.protocol,
    s.delivery_mode,
    s.queue_to_queue
FROM dba_queue_subscribers s
WHERE s.owner = :queue_owner
  AND s.queue_name = :queue_name
ORDER BY s.consumer_name, s.address;

PROMPT
PROMPT === Propagation schedules ===
PROMPT

SELECT
    qs.schema AS owner,
    qs.qname AS queue_name,
    qs.destination,
    TO_CHAR(qs.start_date, 'YYYY-MM-DD HH24:MI:SS') AS schedule_start,
    qs.latency,
    TO_CHAR(qs.last_run_date, 'YYYY-MM-DD HH24:MI:SS') AS last_run,
    TO_CHAR(qs.next_run_date, 'YYYY-MM-DD HH24:MI:SS') AS next_run,
    qs.failures,
    qs.schedule_disabled
FROM dba_queue_schedules qs
WHERE qs.schema = :queue_owner
  AND qs.qname = :queue_name
ORDER BY qs.destination;

PROMPT
PROMPT === Message counts (V$AQ) ===
PROMPT

SELECT
    q.owner,
    q.name AS queue_name,
    aq.waiting,
    aq.ready,
    aq.expired,
    aq.total_wait,
    aq.average_wait
FROM dba_queues q
JOIN v$aq aq
  ON aq.qid = q.qid
WHERE q.owner = :queue_owner
  AND q.name = :queue_name;

PROMPT
PROMPT === Persistent queue stats (GV$PERSISTENT_QUEUES) ===
PROMPT
PROMPT Enq/Deq Time are hundredths of a second spent in enqueue and dequeue.
PROMPT

SELECT
    pq.inst_id,
    q.owner,
    q.name AS queue_name,
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
WHERE q.owner = :queue_owner
  AND q.name = :queue_name
ORDER BY pq.inst_id;

COLUMN owner CLEAR
COLUMN queue_name CLEAR
COLUMN queue_table CLEAR
COLUMN queue_type CLEAR
COLUMN qid CLEAR
COLUMN enqueue_enabled CLEAR
COLUMN dequeue_enabled CLEAR
COLUMN max_retries CLEAR
COLUMN retry_delay CLEAR
COLUMN retention CLEAR
COLUMN user_comment CLEAR
COLUMN object_type CLEAR
COLUMN sort_order CLEAR
COLUMN recipients CLEAR
COLUMN message_grouping CLEAR
COLUMN compatible CLEAR
COLUMN secure CLEAR
COLUMN consumer_name CLEAR
COLUMN address CLEAR
COLUMN protocol CLEAR
COLUMN delivery_mode CLEAR
COLUMN queue_to_queue CLEAR
COLUMN destination CLEAR
COLUMN schedule_start CLEAR
COLUMN latency CLEAR
COLUMN last_run CLEAR
COLUMN next_run CLEAR
COLUMN failures CLEAR
COLUMN schedule_disabled CLEAR
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
COLUMN c_arg1 CLEAR
COLUMN c_arg2 CLEAR

SET NULL ''
SET FEEDBACK ON
SET VERIFY ON
