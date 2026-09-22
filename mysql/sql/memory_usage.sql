/*******************************************************************************
*
* Script Name: memory_usage.sql
* Title: Global memory usage by subsystem
* Tags: Memory, Performance, System
* Purpose: Reports memory allocated across MySQL engines, buffers, and internal events
*
* Description:
*   Queries memory summary events in Performance Schema to identify top memory
*   consumers, current allocation in MB, high-water mark, and active allocation counts.
*
* Parameters:
*   None
*
* Required Privileges:
*   - SELECT on performance_schema.memory_summary_global_by_event_name
*
* Output Format:
*   - event_name: Subsystem or memory instrument name
*   - current_alloc_mb: Memory currently allocated in MB
*   - high_water_mb: Peak memory allocated in MB
*   - current_alloc_count: Number of active memory blocks allocated
*   - total_allocations: Lifetime allocation operations
*
* Example Usage:
*   mysql -u root -p < memory_usage.sql
*   mysql> source memory_usage.sql;
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/

SELECT
    event_name,
    ROUND(current_number_of_bytes_used / 1024 / 1024, 2) AS current_alloc_mb,
    ROUND(high_number_of_bytes_used / 1024 / 1024, 2) AS high_water_mb,
    current_count_used AS current_alloc_count,
    count_alloc AS total_allocations
FROM performance_schema.memory_summary_global_by_event_name
WHERE current_number_of_bytes_used > 0
ORDER BY current_number_of_bytes_used DESC
LIMIT 30;
