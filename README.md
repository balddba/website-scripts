# website-scripts

Canonical files for the [balddba.com](https://balddba.com/scripts) script repository.

The website does not edit these files. Add a script under `{platform}/{language}/`, merge to `main`, and the site syncs from git.

## Layout

```text
linux/{shell,python,rust}/
mysql/{sql,python,shell}/
oracle/{sql,python,shell,rust}/
postgres/{sql,python,shell}/
```

Create a language folder only when it has a file.

| Platform | Use for |
| --- | --- |
| `linux` | Host and OS work |
| `mysql` | MySQL / InnoDB |
| `oracle` | Oracle Database, Grid, RMAN |
| `postgres` | PostgreSQL |

| Language | Extensions | Comment prefix |
| --- | --- | --- |
| `shell` | `.sh`, `.bash` | `#` |
| `sql` | `.sql` | `/* */` |
| `python` | `.py` | `#` |
| `rust` | `.rs` | `//` |

Keep Rust entries as single-file snippets. A real Cargo project belongs in its own repository.

## File header

Put metadata in leading comments. Platform and language come from the path; the URL id comes from the filename (`blocking_sessions.sql` becomes `blocking-sessions`).

```sql
/*******************************************************************************
*
* Script Name: blocking_sessions.sql
* Title: Blocking sessions
* Tags: Performance, Locks
* Purpose: Lists blockers and waiters from GV$SESSION.
*
* Author: Aaron Myers <aaron@balddba.com>
*
*******************************************************************************/
```

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

- `title` / `Title` is the heading on the site. If omitted, the filename is used.
- `tags` / `Tags` is a comma-separated list. If omitted, the script has no tags.
- Remaining header comments become the description. `Purpose` is used when present. Python files with no extra comment prose use the module docstring.
- Every file includes `Author: Aaron Myers <aaron@balddba.com>`. Start from `templates/`.

## How the site updates

1. Merge to `main`.
2. GitHub Actions (or a repository webhook) `POST`s to `https://balddba.com/api/scripts/sync`.
3. The API walks `{platform}/{language}/*`, reads each header, and replaces the `scripts` table.

Local site development can mount this checkout and set `SCRIPTS_LOCAL_PATH` instead of calling GitHub.

### GitHub Actions secrets

| Secret | Value |
| --- | --- |
| `SITE_SYNC_URL` | `https://balddba.com/api/scripts/sync` |
| `SITE_SYNC_SECRET` | Same string as `SCRIPTS_WEBHOOK_SECRET` on the API |

### Repository webhook (optional)

- Payload URL: `https://balddba.com/api/scripts/sync`
- Content type: `application/json`
- Secret: `SCRIPTS_WEBHOOK_SECRET`
- Event: `push`
