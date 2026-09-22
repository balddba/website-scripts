/*******************************************************************************
*
* Script Name: active_queries.sql
* Title: Active running queries
* Tags: Performance, Sessions, Activity
* Purpose: Reports currently executing queries excluding idle/sleep connections
*
* Description:
*   Inspects the MySQL processlist to display currently executing client queries,
*   including execution elapsed time, current execution state, user, client host,
*   database, and SQL text.
*
* Parameters:
*   None
*
* Required Privileges:
*   - PROCESS
*
* Output Format:
*   - conn_id: Connection / thread ID
*   - user: Connected user
*   - host: Client host / IP
*   - db: Current default database
*   - command: Command type (Query, Execute, etc.)
*   - elapsed_sec: Execution duration in seconds
*   - state: Current execution thread state
*   - sql_text: SQL statement text
*
* Example Usage:
*   mysql -u root -p < active_queries.sql
*   mysql> source active_queries.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    id AS conn_id,
    user,
    host,
    COALESCE(db, '') AS db,
    command,
    time AS elapsed_sec,
    COALESCE(state, '') AS state,
    info AS sql_text
FROM information_schema.processlist
WHERE command != 'Sleep'
  AND id != CONNECTION_ID()
ORDER BY time DESC;
