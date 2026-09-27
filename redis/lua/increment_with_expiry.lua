--=============================================================================
--
-- Script Name: increment_with_expiry.lua
-- Title: Increment a counter with expiry
-- Tags: Redis, Lua, Counters, TTL
-- Purpose: Atomically increments a counter and ensures it has an expiration.
--
-- Description:
--   Increments a string counter and sets its TTL when the key has no expiry.
--   This is useful for short-lived counters such as request or event totals.
--
-- Parameters:
--   KEYS[1] - Counter key
--   ARGV[1] - TTL in seconds (positive integer)
--   ARGV[2] - Optional increment amount (integer, defaults to 1)
--
-- Required Privileges:
--   - EVAL or EVALSHA
--   - INCRBY, TTL, and EXPIRE for the target key
--
-- Output Format:
--   Two-element array: new counter value, remaining TTL in seconds
--
-- Example Usage:
--   redis-cli --eval increment_with_expiry.lua api:requests:minute , 60 1
--
-- Author: Aaron Myers <aaron@balddba.com>
--
--=============================================================================

local key = KEYS[1]
local ttl = tonumber(ARGV[1])
local increment = tonumber(ARGV[2] or "1")

if not key or key == "" then
    return redis.error_reply("KEYS[1] must be a non-empty counter key")
end

if not ttl or ttl <= 0 or ttl ~= math.floor(ttl) then
    return redis.error_reply("ARGV[1] must be a positive integer TTL")
end

if not increment or increment ~= math.floor(increment) then
    return redis.error_reply("ARGV[2] must be an integer increment")
end

local value = redis.call("INCRBY", key, increment)
if redis.call("TTL", key) == -1 then
    redis.call("EXPIRE", key, ttl)
end

return { value, redis.call("TTL", key) }
