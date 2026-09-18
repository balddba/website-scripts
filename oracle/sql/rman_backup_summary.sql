/*******************************************************************************
*
* Script Name: rman_backup_summary.sql
* Title: RMAN backup summary
* Tags: RMAN, Backup
* Purpose: Display a summary of recent RMAN backup jobs from V$RMAN_BACKUP_JOB_DETAILS
*
* Description:
*   Lists RMAN backup jobs from the last 7 days with status, elapsed time,
*   and output size.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$RMAN_BACKUP_JOB_DETAILS
*
* Output Format:
*   - Session key, input type, status, start/end time
*   - Elapsed minutes and output size in GB
*
* Example Usage:
*   sqlplus user/password@yourdb @rman_backup_summary.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    session_key,
    input_type,
    status,
    start_time,
    end_time,
    ROUND(elapsed_seconds / 60, 1) AS elapsed_min,
    ROUND(output_bytes / 1024 / 1024 / 1024, 2) AS output_gb
FROM v$rman_backup_job_details
WHERE start_time > SYSDATE - 7
ORDER BY start_time DESC;
