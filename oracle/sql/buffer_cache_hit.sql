/*******************************************************************************
*
* Script Name: buffer_cache_hit.sql
* Title: Buffer cache hit ratio
* Tags: Memory, Buffer Cache, Performance
* Purpose: Report buffer cache hit ratio from V$SYSSTAT and per-pool stats from V$BUFFER_POOL_STATISTICS
*
* Description:
*   Shows instance uptime, the classic buffer cache hit ratio, and a
*   cache-only ratio that excludes direct-path reads. Classic ratio is
*   1 - physical reads / (db block gets + consistent gets). Cache-only
*   uses physical reads cache over cache gets and is the better health
*   signal when DSS or parallel query does direct reads. Pool-level
*   gets, physical reads, and wait counts come from
*   V$BUFFER_POOL_STATISTICS. Ratios are cumulative since instance
*   start; a high ratio does not prove the cache is sized well.
*
* Parameters:
*   None.
*
* Required Privileges:
*   - SELECT on V$INSTANCE
*   - SELECT on V$SYSSTAT
*   - SELECT on V$BUFFER_POOL
*   - SELECT on V$BUFFER_POOL_STATISTICS
*   - Or SELECT_CATALOG_ROLE
*
* Output Format:
*   - Instance name, startup time, and uptime hours
*   - Logical reads, physical reads, and hit ratios (percent)
*   - Direct-path vs cache physical reads
*   - Per buffer pool: size, gets, physical reads, hit percent, and waits
*
* Example Usage:
*   SQL> @buffer_cache_hit.sql
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

COLUMN instance_name        FORMAT A16               HEADING 'Instance'
COLUMN host_name            FORMAT A24 TRUNC         HEADING 'Host'
COLUMN startup_time         FORMAT A19               HEADING 'Startup'
COLUMN uptime_hours         FORMAT 999,990.0         HEADING 'Uptime Hrs'
COLUMN db_block_gets        FORMAT 999,999,999,990   HEADING 'DB Block Gets'
COLUMN consistent_gets      FORMAT 999,999,999,990   HEADING 'Consistent Gets'
COLUMN logical_reads        FORMAT 999,999,999,990   HEADING 'Logical Reads'
COLUMN physical_reads       FORMAT 999,999,999,990   HEADING 'Physical Reads'
COLUMN phys_reads_cache     FORMAT 999,999,999,990   HEADING 'Phys Cache'
COLUMN phys_reads_direct    FORMAT 999,999,999,990   HEADING 'Phys Direct'
COLUMN classic_hit_pct      FORMAT 990.00            HEADING 'Classic Hit %'
COLUMN cache_hit_pct        FORMAT 990.00            HEADING 'Cache Hit %'
COLUMN pool_name            FORMAT A12               HEADING 'Pool'
COLUMN block_size           FORMAT 999,999           HEADING 'Blk Size'
COLUMN size_mb              FORMAT 999,999,990.0     HEADING 'Size MB'
COLUMN buffers              FORMAT 999,999,990       HEADING 'Buffers'
COLUMN free_buffer_wait     FORMAT 999,999,990       HEADING 'Free Buf Wait'
COLUMN write_complete_wait  FORMAT 999,999,990       HEADING 'Write Cmpl Wait'
COLUMN buffer_busy_wait     FORMAT 999,999,990       HEADING 'Buf Busy Wait'

PROMPT
PROMPT === Instance ===
PROMPT

SELECT
    instance_name,
    host_name,
    TO_CHAR(startup_time, 'YYYY-MM-DD HH24:MI:SS') AS startup_time,
    ROUND((SYSDATE - startup_time) * 24, 1) AS uptime_hours
FROM v$instance;

PROMPT
PROMPT === Buffer cache hit ratio ===
PROMPT

SELECT
    s.db_block_gets,
    s.consistent_gets,
    s.db_block_gets + s.consistent_gets AS logical_reads,
    s.physical_reads,
    s.phys_reads_cache,
    s.phys_reads_direct,
    ROUND(
        (1 - s.physical_reads
            / NULLIF(s.db_block_gets + s.consistent_gets, 0)
        ) * 100,
        2
    ) AS classic_hit_pct,
    ROUND(
        (1 - s.phys_reads_cache
            / NULLIF(s.db_block_gets_cache + s.consistent_gets_cache, 0)
        ) * 100,
        2
    ) AS cache_hit_pct
FROM (
    SELECT
        SUM(CASE WHEN name = 'db block gets' THEN value END) AS db_block_gets,
        SUM(CASE WHEN name = 'consistent gets' THEN value END) AS consistent_gets,
        SUM(CASE WHEN name = 'physical reads' THEN value END) AS physical_reads,
        SUM(CASE WHEN name = 'physical reads cache' THEN value END) AS phys_reads_cache,
        SUM(CASE WHEN name = 'physical reads direct' THEN value END) AS phys_reads_direct,
        SUM(CASE WHEN name = 'db block gets from cache' THEN value END) AS db_block_gets_cache,
        SUM(CASE WHEN name = 'consistent gets from cache' THEN value END) AS consistent_gets_cache
    FROM v$sysstat
    WHERE name IN (
        'db block gets',
        'consistent gets',
        'physical reads',
        'physical reads cache',
        'physical reads direct',
        'db block gets from cache',
        'consistent gets from cache'
    )
) s;

PROMPT
PROMPT === Buffer pool statistics ===
PROMPT

SELECT
    p.name AS pool_name,
    p.block_size,
    p.current_size AS size_mb,
    p.buffers,
    s.db_block_gets,
    s.consistent_gets,
    s.physical_reads,
    ROUND(
        (1 - s.physical_reads
            / NULLIF(s.db_block_gets + s.consistent_gets, 0)
        ) * 100,
        2
    ) AS classic_hit_pct,
    s.free_buffer_wait,
    s.write_complete_wait,
    s.buffer_busy_wait
FROM v$buffer_pool p
LEFT JOIN v$buffer_pool_statistics s
    ON s.id = p.id
ORDER BY p.block_size, p.name;

COLUMN instance_name CLEAR
COLUMN host_name CLEAR
COLUMN startup_time CLEAR
COLUMN uptime_hours CLEAR
COLUMN db_block_gets CLEAR
COLUMN consistent_gets CLEAR
COLUMN logical_reads CLEAR
COLUMN physical_reads CLEAR
COLUMN phys_reads_cache CLEAR
COLUMN phys_reads_direct CLEAR
COLUMN classic_hit_pct CLEAR
COLUMN cache_hit_pct CLEAR
COLUMN pool_name CLEAR
COLUMN block_size CLEAR
COLUMN size_mb CLEAR
COLUMN buffers CLEAR
COLUMN free_buffer_wait CLEAR
COLUMN write_complete_wait CLEAR
COLUMN buffer_busy_wait CLEAR

SET FEEDBACK ON
SET VERIFY ON
