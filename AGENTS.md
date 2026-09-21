# Agent Instructions

## Script import
balddba.com imports every file under `{platform}/{language}/`. It does not use a catalog JSON.

## Required header tags
Put these in leading comments, before any code. The importer ignores the rest of the file for metadata.

| Tag | Required | Notes |
| --- | --- | --- |
| `title:` | yes | Site heading |
| `tags:` | yes | Comma-separated chips, e.g. `Performance, Locks` |
| `id:` | no | Defaults from the filename: `blocking_sessions.sql` → `blocking-sessions` |

Comment prefixes: `#` (shell, python), `/* */` (sql), `//` (rust). Put `Title`, `Tags`, `Purpose`, and `Author` in the leading boxed header.

Every file includes `Author: Aaron Myers <aaron@balddba.com>`. Third-party files keep the original author and add this as Author/Maintainer.

```bash
#!/usr/bin/env bash
#===============================================================================
#
# Script Name: crs_health.sh
# Title: CRS health snapshot
# Tags: RAC, Grid
# Purpose: Prints CRS status, resource tree, and voting disks.
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
```

## Path
- `{platform}/{language}/{filename}` only.
- Platforms: `linux`, `mysql`, `oracle`, `postgres`.
- Languages: `shell` (`.sh`, `.bash`), `sql` (`.sql`), `python` (`.py`), `rust` (`.rs`).
- Create a language folder only when it has a file.

## New files
Start from the matching template in `templates/`. Copy the boxed header and fill in Title, Tags, Purpose, Description, Parameters, Required Privileges, Output Format, Example Usage, and Author.

| Kind | Template |
| --- | --- |
| Shell scripts | `templates/shell-script.sh` |
| SQL scripts | `templates/sql-script.sql` |
| Python scripts | `templates/python-script.py` |
| RMAN command files | `templates/rman-command.rman` |
| Cron entries | `templates/cron-entry.txt` |
| Documentation | `templates/README-template.md` |

- Bash scripts use `#!/usr/bin/env bash`
- Use `set -uo pipefail`
- Define `usage()` and `fail()` helpers
- Validate inputs before touching Oracle/RMAN

## External References
| Need | File |
| --- | --- |
| Layout, examples, site sync | `README.md` |
| New-file templates | `templates/` |

## Running tests
Parser tests: `uv run pytest tests/oracle/test_script_parser.py`

Oracle integration tests need `.env` with `ORACLE_TEST_USER`, `ORACLE_TEST_PASSWORD`, `ORACLE_TEST_CONNECT`, and `ORACLE_TEST_SCHEMA`. Set `ORACLE_TEST_ALLOW_INSTANCE_DDL=1` only against a disposable PDB. Incomplete credentials skip live-Oracle tests. See `README.md`.
