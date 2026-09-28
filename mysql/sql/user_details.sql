/*******************************************************************************
*
* Script Name: user_details.sql
* Title: Detailed user report
* Tags: Security, Users, Accounts
* Purpose: Reports authentication, password, and resource-limit details for MySQL accounts
*
* Description:
*   Displays account details from mysql.user for all accounts, or for a specific
*   user and host when the optional session variables are set before sourcing
*   the script.
*
* Parameters:
*   @mysql_user_name - (Optional) Account user name to report
*   @mysql_user_host - (Optional) Account host to report
*
* Required Privileges:
*   - SELECT on mysql.user
*
* Output Format:
*   - user: Account user name
*   - host: Account host
*   - account_locked: Whether the account is locked
*   - password_expired: Whether the password is expired
*   - password_last_changed: Password last changed timestamp
*   - password_lifetime: Password lifetime in days
*   - max_queries: Max queries per hour
*   - max_updates: Max updates per hour
*   - max_connections: Max connections per hour
*   - max_user_connections: Max simultaneous connections for account
*   - plugin: Authentication plugin
*
* Example Usage:
*   mysql -u root -p < user_details.sql
*   mysql> SET @mysql_user_name = 'app_user';
*   mysql> SET @mysql_user_host = '%';
*   mysql> source user_details.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    user,
    host,
    account_locked,
    password_expired,
    password_last_changed,
    password_lifetime,
    max_questions AS max_queries,
    max_updates,
    max_connections,
    max_user_connections,
    plugin
FROM mysql.user
WHERE (@mysql_user_name IS NULL OR user = @mysql_user_name)
  AND (@mysql_user_host IS NULL OR host = @mysql_user_host)
ORDER BY user, host;
