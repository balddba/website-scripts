--=============================================================================
--
-- Script Name: fixed_window_rate_limit.lua
-- Title: Fixed-window rate limiter
-- Tags: Redis, Lua, Rate Limiting, Counters
-- Purpose: Atomically checks and increments a fixed-window request counter.
--
-- Description:
--   Counts requests in a fixed time window and reports whether the current
--   request is allowed. Use a distinct colon-separated key for each subject
--   and window, such as rate:user:42:20260926T1200.
--
-- Parameters:
--   KEYS[1] - Counter key for the subject and current window
--   ARGV[1] - Maximum requests allowed in the window (positive integer)
--   ARGV[2] - Window duration in seconds (positive integer)
--
-- Required Privileges:
--   - EVAL or EVALSHA
--   - INCR, TTL, and EXPIRE for the target key
--
-- Output Format:
--   Three-element array: allowed flag (1 or 0), request count, remaining TTL
--
-- Example Usage:
--   redis-cli --eval fixed_window_rate_limit.lua rate:user:42:minute , 100 60
--
-- Author: Aaron Myers <aaron@balddba.com>
--
--=============================================================================

local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

if not key or key == "" then
    return redis.error_reply("KEYS[1] must be a non-empty counter key")
end

if not limit or limit <= 0 or limit ~= math.floor(limit) then
    return redis.error_reply("ARGV[1] must be a positive integer limit")
end

if not window or window <= 0 or window ~= math.floor(window) then
    return redis.error_reply("ARGV[2] must be a positive integer window")
end

local count = redis.call("INCR", key)
if redis.call("TTL", key) == -1 then
    redis.call("EXPIRE", key, window)
end

local allowed = 0
if count <= limit then
    allowed = 1
end

return { allowed, count, redis.call("TTL", key) }
