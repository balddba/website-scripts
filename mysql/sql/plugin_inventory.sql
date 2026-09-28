/*******************************************************************************
*
* Script Name: plugin_inventory.sql
* Title: Plugin inventory
* Tags: Plugins, Metadata, Configuration
* Purpose: Displays installed MySQL plugins and their status
*
* Description:
*   Lists plugins known to the server, including version, status, plugin type,
*   load option, and license for quick configuration and feature review.
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT on information_schema.plugins
*
* Output Format:
*   - plugin_name: Plugin name
*   - plugin_version: Plugin version
*   - plugin_status: ACTIVE, DISABLED, or other server status
*   - plugin_type: Plugin category
*   - load_option: Startup/load behavior
*   - license: Plugin license
*
* Example Usage:
*   mysql -u root -p < plugin_inventory.sql
*   mysql> source plugin_inventory.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    plugin_name,
    plugin_version,
    plugin_status,
    plugin_type,
    load_option,
    plugin_license AS license
FROM information_schema.plugins
ORDER BY plugin_type, plugin_name;
