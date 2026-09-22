/*******************************************************************************
*
* Script Name: blocking_transactions.sql
* Title: InnoDB lock waits and blocking transactions
* Tags: Locks, Performance, Transactions
* Purpose: Reports blocked queries, lock modes, and the blocking process holding the lock
*
* Description:
*   Queries sys.innodb_lock_waits to display active lock contentions, identifying
*   the waiting thread, blocking thread ID, affected table/index, lock modes,
*   and transaction age.
*
* Parameters:
*   None
*
* Required Privileges:
*   - PROCESS (or SELECT on sys.innodb_lock_waits, performance_schema)
*
* Output Format:
*   - waiting_pid: Process ID of the blocked query
*   - waiting_query: SQL statement currently waiting on a lock
*   - wait_age: Time the query has been waiting for the lock
*   - locked_table: Table being locked
*   - locked_index: Index on which the lock was requested
*   - waiting_lock_mode: Requested lock mode (X, S, etc.)
*   - blocking_pid: Process ID holding the blocking lock
*   - blocking_query: Current or last statement of the blocker
*   - blocking_trx_age: Total active duration of the blocking transaction
*   - blocking_lock_mode: Lock mode held by the blocker
*
* Example Usage:
*   mysql -u root -p < blocking_transactions.sql
*   mysql> source blocking_transactions.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    waiting_pid,
    waiting_query,
    wait_age,
    locked_table,
    locked_index,
    waiting_lock_mode,
    blocking_pid,
    COALESCE(blocking_query, '<idle in transaction>') AS blocking_query,
    blocking_trx_age,
    blocking_lock_mode
FROM sys.innodb_lock_waits
ORDER BY wait_age DESC;
