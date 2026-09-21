/*******************************************************************************
*
* Script Name: flash_recovery_area.sql
* Title: Flash Recovery Area
* Tags: Capacity, RMAN, FRA, Backup
* Purpose: Report FRA location, size, used and reclaimable space, and usage by file type
*
* Description:
*   Shows Fast Recovery Area (formerly Flash Recovery Area) configuration and
*   space. V$RECOVERY_FILE_DEST has the location, size limit, used bytes,
*   reclaimable bytes, and file count. Reclaimable space is obsolete backups,
*   copies, and logs Oracle can delete when the FRA is under pressure.
*   V$RECOVERY_AREA_USAGE breaks used and reclaimable percent down by file
*   type. Archive destinations that write into the FRA and flashback database
*   log retention are included. FRA is a database-level setting; run this from
*   CDB$ROOT on a container database.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$DATABASE
*   - SELECT on V$PARAMETER
*   - SELECT on V$RECOVERY_FILE_DEST
*   - SELECT on V$RECOVERY_AREA_USAGE
*   - SELECT on V$ARCHIVE_DEST
*   - SELECT on V$FLASHBACK_DATABASE_LOG
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Database archive mode and flashback status
*   - FRA parameters (location, size, flashback retention)
*   - Space limit, used, reclaimable, percent used, and file count
*   - Used and reclaimable percent by file type
*   - Archive destinations that use the FRA
*   - Flashback log oldest time, retention, and estimated size
*
* Example Usage:
*   SQL> @flash_recovery_area.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET FEEDBACK OFF
SET LINESIZE 220
SET PAGESIZE 100
SET TRIMSPOOL ON
SET TAB OFF

COLUMN db_name              FORMAT A20               HEADING 'DB Name'
COLUMN log_mode             FORMAT A12               HEADING 'Log Mode'
COLUMN flashback_on         FORMAT A12               HEADING 'Flashback'
COLUMN parameter            FORMAT A36               HEADING 'Parameter'
COLUMN value                FORMAT A80               HEADING 'Value'
COLUMN fra_location         FORMAT A60               HEADING 'FRA Location'
COLUMN limit_gb             FORMAT 999,999,990.0     HEADING 'Limit GB'
COLUMN used_gb              FORMAT 999,999,990.0     HEADING 'Used GB'
COLUMN reclaimable_gb       FORMAT 999,999,990.0     HEADING 'Reclaim GB'
COLUMN used_nonreclaim_gb   FORMAT 999,999,990.0     HEADING 'Non-Recl GB'
COLUMN free_gb              FORMAT 999,999,990.0     HEADING 'Free GB'
COLUMN pct_used             FORMAT 990.0             HEADING 'Pct Used'
COLUMN pct_nonreclaim       FORMAT 990.0             HEADING 'Pct Non-Recl'
COLUMN number_of_files      FORMAT 999,999,990       HEADING 'Files'
COLUMN file_type            FORMAT A28               HEADING 'File Type'
COLUMN percent_space_used   FORMAT 990.0             HEADING 'Pct Used'
COLUMN percent_reclaimable  FORMAT 990.0             HEADING 'Pct Reclaim'
COLUMN percent_nonreclaim   FORMAT 990.0             HEADING 'Pct Non-Recl'
COLUMN dest_id              FORMAT 999               HEADING 'Dest'
COLUMN dest_name            FORMAT A20               HEADING 'Dest Name'
COLUMN status               FORMAT A10               HEADING 'Status'
COLUMN binding              FORMAT A10               HEADING 'Binding'
COLUMN target               FORMAT A10               HEADING 'Target'
COLUMN destination          FORMAT A50               HEADING 'Destination'
COLUMN valid_type           FORMAT A16               HEADING 'Valid Type'
COLUMN error                FORMAT A50 TRUNC         HEADING 'Error'
COLUMN oldest_scn           FORMAT 999999999999999   HEADING 'Oldest SCN'
COLUMN oldest_flashback     FORMAT A19               HEADING 'Oldest Flashback'
COLUMN retention_min        FORMAT 999,999           HEADING 'Retain Min'
COLUMN flashback_gb         FORMAT 999,999,990.0     HEADING 'Flashback GB'
COLUMN estimated_gb         FORMAT 999,999,990.0     HEADING 'Estimated GB'

PROMPT
PROMPT === Database ===
PROMPT

SELECT
    name AS db_name,
    log_mode,
    flashback_on
FROM v$database;

PROMPT
PROMPT === FRA parameters ===
PROMPT

SELECT
    name AS parameter,
    NVL(display_value, '(not set)') AS value
FROM v$parameter
WHERE name IN (
    'db_recovery_file_dest',
    'db_recovery_file_dest_size',
    'db_flashback_retention_target'
)
ORDER BY name;

PROMPT
PROMPT === FRA space ===
PROMPT

SELECT
    name AS fra_location,
    ROUND(space_limit / 1024 / 1024 / 1024, 1) AS limit_gb,
    ROUND(space_used / 1024 / 1024 / 1024, 1) AS used_gb,
    ROUND(space_reclaimable / 1024 / 1024 / 1024, 1) AS reclaimable_gb,
    ROUND((space_used - space_reclaimable) / 1024 / 1024 / 1024, 1) AS used_nonreclaim_gb,
    ROUND((space_limit - space_used) / 1024 / 1024 / 1024, 1) AS free_gb,
    ROUND(space_used / NULLIF(space_limit, 0) * 100, 1) AS pct_used,
    ROUND((space_used - space_reclaimable) / NULLIF(space_limit, 0) * 100, 1) AS pct_nonreclaim,
    number_of_files
FROM v$recovery_file_dest
ORDER BY name;

PROMPT
PROMPT === Usage by file type ===
PROMPT

SELECT
    file_type,
    number_of_files,
    percent_space_used,
    percent_space_reclaimable AS percent_reclaimable,
    ROUND(percent_space_used - percent_space_reclaimable, 1) AS percent_nonreclaim
FROM v$recovery_area_usage
ORDER BY percent_space_used DESC, file_type;

PROMPT
PROMPT === Archive destinations using the FRA ===
PROMPT

SELECT
    d.dest_id,
    d.dest_name,
    d.status,
    d.binding,
    d.target,
    d.destination,
    d.valid_type,
    d.error
FROM v$archive_dest d
WHERE d.destination = 'USE_DB_RECOVERY_FILE_DEST'
   OR d.destination IN (
        SELECT name
        FROM v$recovery_file_dest
        WHERE name IS NOT NULL
    )
ORDER BY d.dest_id;

PROMPT
PROMPT === Flashback database log ===
PROMPT

SELECT
    oldest_flashback_scn AS oldest_scn,
    TO_CHAR(oldest_flashback_time, 'YYYY-MM-DD HH24:MI:SS') AS oldest_flashback,
    retention_target AS retention_min,
    ROUND(flashback_size / 1024 / 1024 / 1024, 1) AS flashback_gb,
    ROUND(estimated_flashback_size / 1024 / 1024 / 1024, 1) AS estimated_gb
FROM v$flashback_database_log;

COLUMN db_name CLEAR
COLUMN log_mode CLEAR
COLUMN flashback_on CLEAR
COLUMN parameter CLEAR
COLUMN value CLEAR
COLUMN fra_location CLEAR
COLUMN limit_gb CLEAR
COLUMN used_gb CLEAR
COLUMN reclaimable_gb CLEAR
COLUMN used_nonreclaim_gb CLEAR
COLUMN free_gb CLEAR
COLUMN pct_used CLEAR
COLUMN pct_nonreclaim CLEAR
COLUMN number_of_files CLEAR
COLUMN file_type CLEAR
COLUMN percent_space_used CLEAR
COLUMN percent_reclaimable CLEAR
COLUMN percent_nonreclaim CLEAR
COLUMN dest_id CLEAR
COLUMN dest_name CLEAR
COLUMN status CLEAR
COLUMN binding CLEAR
COLUMN target CLEAR
COLUMN destination CLEAR
COLUMN valid_type CLEAR
COLUMN error CLEAR
COLUMN oldest_scn CLEAR
COLUMN oldest_flashback CLEAR
COLUMN retention_min CLEAR
COLUMN flashback_gb CLEAR
COLUMN estimated_gb CLEAR

SET FEEDBACK ON
SET VERIFY ON
