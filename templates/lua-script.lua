--=============================================================================
--
-- Script Name: script_name.lua
-- Title: Script title
-- Tags: Redis, Lua
-- Purpose: One-line description of what the script does.
--
-- Description:
--   Describe the operation and why it must execute atomically in Redis.
--
-- Parameters:
--   KEYS[1] - Redis key used by the script
--   ARGV[1] - First script argument
--
-- Required Privileges:
--   - Permission to run EVAL or EVALSHA
--   - Permission to execute each Redis command used below
--
-- Output Format:
--   Describe the returned scalar or array values.
--
-- Example Usage:
--   redis-cli --eval script_name.lua example:key , argument
--
-- Author: Aaron Myers <aaron@balddba.com>
--
--=============================================================================

local key = KEYS[1]
local argument = ARGV[1]

return { key, argument }
