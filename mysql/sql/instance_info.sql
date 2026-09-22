/*******************************************************************************
*
* Script Name: instance_info.sql
* Title: Instance and server information
* Tags: Configuration, Instance, System
* Purpose: Reports MySQL server version, uptime, connection limits, and system settings
*
* Description:
*   Retrieves core MySQL instance information including version, uptime,
*   server ID, UUID, hostname, read-only mode, max connections, current
*   thread counts, and default storage engine.
*
* Parameters:
*   None
*
* Required Privileges:
*   - PROCESS (or SELECT on performance_schema / information_schema)
*
* Output Format:
*   - metric: Name of the server attribute or metric
*   - value: Current configuration value or runtime metric
*
* Example Usage:
*   mysql -u root -p < instance_info.sql
*   mysql> source instance_info.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    'Version' AS metric,
    @@version AS value
UNION ALL
SELECT
    'Version Comment',
    @@version_comment
UNION ALL
SELECT
    'Server ID',
    CAST(@@server_id AS CHAR)
UNION ALL
SELECT
    'Server UUID',
    @@server_uuid
UNION ALL
SELECT
    'Hostname',
    @@hostname
UNION ALL
SELECT
    'Port',
    CAST(@@port AS CHAR)
UNION ALL
SELECT
    'Socket',
    @@socket
UNION ALL
SELECT
    'Data Directory',
    @@datadir
UNION ALL
SELECT
    'Uptime',
    CONCAT(
        FLOOR(VARIABLE_VALUE / 86400), 'd ',
        FLOOR((VARIABLE_VALUE % 86400) / 3600), 'h ',
        FLOOR((VARIABLE_VALUE % 3600) / 60), 'm ',
        FLOOR(VARIABLE_VALUE % 60), 's'
    )
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Uptime'
UNION ALL
SELECT
    'Read Only',
    IF(@@read_only = 1, 'YES', 'NO')
UNION ALL
SELECT
    'Super Read Only',
    IF(@@super_read_only = 1, 'YES', 'NO')
UNION ALL
SELECT
    'Default Storage Engine',
    @@default_storage_engine
UNION ALL
SELECT
    'Max Connections',
    CAST(@@max_connections AS CHAR)
UNION ALL
SELECT
    'Current Connections',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Threads_connected'
UNION ALL
SELECT
    'Threads Running',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Threads_running'
UNION ALL
SELECT
    'Max Used Connections',
    CAST(VARIABLE_VALUE AS CHAR)
FROM performance_schema.global_status
WHERE VARIABLE_NAME = 'Max_used_connections'
UNION ALL
SELECT
    'Character Set Server',
    @@character_set_server
UNION ALL
SELECT
    'Collation Server',
    @@collation_server;
