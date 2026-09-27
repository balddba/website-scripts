--=============================================================================
--
-- Script Name: compare_and_delete.lua
-- Title: Compare and delete a key
-- Tags: Redis, Lua, Locks, Atomic
-- Purpose: Deletes a key only when its value matches the supplied token.
--
-- Description:
--   Performs an atomic ownership check before deleting a key. This is commonly
--   used to release a simple lock without deleting a lock acquired by another
--   client after the original lock expired.
--
-- Parameters:
--   KEYS[1] - Key to compare and delete
--   ARGV[1] - Expected value or lock token
--
-- Required Privileges:
--   - EVAL or EVALSHA
--   - GET and DEL for the target key
--
-- Output Format:
--   1 when the key was deleted; 0 when it was absent or did not match
--
-- Example Usage:
--   redis-cli --eval compare_and_delete.lua lock:report:daily , worker-123
--
-- Author: Aaron Myers <aaron@balddba.com>
--
--=============================================================================

local key = KEYS[1]
local expected = ARGV[1]

if not key or key == "" then
    return redis.error_reply("KEYS[1] must be a non-empty key")
end

if not expected then
    return redis.error_reply("ARGV[1] must contain the expected value")
end

if redis.call("GET", key) == expected then
    return redis.call("DEL", key)
end

return 0
