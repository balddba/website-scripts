/*******************************************************************************
*
* Script Name: replication_status.sql
* Title: Replication status
* Tags: Replication, Monitoring
* Purpose: Reports configured replication channels and their current state
*
* Description:
*   Reads Performance Schema replication connection and applier tables to show
*   source connection details, service state, received transaction set, and the
*   latest recorded connection error for each channel.
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT on performance_schema.replication_connection_configuration
*   - SELECT on performance_schema.replication_connection_status
*
* Output Format:
*   - channel_name: Replication channel name
*   - source_host: Configured source host
*   - source_port: Configured source port
*   - service_state: Connection service state
*   - received_transaction_set: GTID set received on the channel
*   - last_error_number: Last connection error number
*   - last_error_message: Last connection error text
*   - last_error_timestamp: Last connection error timestamp
*
* Example Usage:
*   mysql -u root -p < replication_status.sql
*   mysql> source replication_status.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    config.channel_name,
    config.host AS source_host,
    config.port AS source_port,
    COALESCE(status.service_state, 'NOT RUNNING') AS service_state,
    COALESCE(status.received_transaction_set, '') AS received_transaction_set,
    COALESCE(status.last_error_number, 0) AS last_error_number,
    COALESCE(status.last_error_message, '') AS last_error_message,
    status.last_error_timestamp
FROM performance_schema.replication_connection_configuration AS config
LEFT JOIN performance_schema.replication_connection_status AS status
    ON status.channel_name = config.channel_name
ORDER BY config.channel_name;
