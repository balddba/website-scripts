/*******************************************************************************
*
* Script Name: feature_usage.sql
* Title: Database feature usage
* Tags: Licensing, Features
* Purpose: Report currently used and previously detected features from DBA_FEATURE_USAGE_STATISTICS
*
* Description:
*   Lists features for the current database where CURRENTLY_USED is TRUE or
*   DETECTED_USAGES is greater than zero. After an upgrade the view can keep
*   one row per version; this script keeps the latest VERSION per feature.
*   Run it in the container you care about (CDB root or a PDB). CURRENTLY_USED
*   can clear after a week of inactivity, so DETECTED_USAGES and the first/last
*   dates still matter for a license review.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on DBA_FEATURE_USAGE_STATISTICS
*   - SELECT on V$DATABASE
*
* Output Format:
*   - Feature name and currently-used flag
*   - Detection count, sample count, and tracked version
*   - First and last usage dates
*
* Example Usage:
*   SQL> @feature_usage.sql
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SET VERIFY OFF
SET LINESIZE 200
SET PAGESIZE 100

COLUMN name            FORMAT A55            HEADING 'Feature'
COLUMN currently_used  FORMAT A8             HEADING 'In Use'
COLUMN detected_usages FORMAT 999,999        HEADING 'Detections'
COLUMN total_samples   FORMAT 999,999        HEADING 'Samples'
COLUMN version         FORMAT A17            HEADING 'Version'
COLUMN first_usage     FORMAT A19            HEADING 'First Used'
COLUMN last_usage      FORMAT A19            HEADING 'Last Used'

SELECT
    u.name,
    u.currently_used,
    u.detected_usages,
    u.total_samples,
    u.version,
    TO_CHAR(u.first_usage_date, 'YYYY-MM-DD HH24:MI:SS') AS first_usage,
    TO_CHAR(u.last_usage_date, 'YYYY-MM-DD HH24:MI:SS') AS last_usage
FROM dba_feature_usage_statistics u
WHERE u.dbid = (SELECT dbid FROM v$database)
  AND u.version = (
        SELECT MAX(u2.version)
        FROM dba_feature_usage_statistics u2
        WHERE u2.name = u.name
          AND u2.dbid = u.dbid
      )
  AND (u.currently_used = 'TRUE' OR u.detected_usages > 0)
ORDER BY
    CASE WHEN u.currently_used = 'TRUE' THEN 0 ELSE 1 END,
    u.name;
