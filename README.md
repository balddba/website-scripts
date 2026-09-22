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

## Running tests

Parser unit tests need only Python. Oracle and MySQL integration tests need database connection settings configured in `.env`.

### Oracle Tests

```bash
cp .env.example .env   # fill ORACLE_TEST_*
uv sync --group dev
uv run pytest tests/oracle
```

Oracle script runs also create `reports/oracle-script-report.html`. The self-contained report includes every returned row, all executed SQL, DBMS output, and execution errors. Because it can contain sensitive database details, `reports/` is ignored by Git. Use `--oracle-report PATH` to choose another location.

| Variable | Purpose |
| --- | --- |
| `ORACLE_TEST_USER` | Database user |
| `ORACLE_TEST_PASSWORD` | Password (never commit `.env`) |
| `ORACLE_TEST_CONNECT` | EZCONNECT string or TNS alias |
| `ORACLE_TEST_SCHEMA` | Schema that owns fixture objects |
| `ORACLE_TEST_ALLOW_INSTANCE_DDL` | `1` only on a throwaway PDB; enables grant-sync and `xplan.package.sql` |

### MySQL Tests

You can spin up a local MySQL test instance using Docker Compose:

```bash
docker compose up -d
cp .env.example .env   # configured for local Docker container by default
uv sync --group dev
uv run pytest tests/mysql
```

MySQL script runs also create `reports/mysql-script-report.html`. The self-contained report includes every returned row, all executed SQL, and execution errors. Use `--mysql-report PATH` to choose another location.

| Variable | Purpose | Default |
| --- | --- | --- |
| `MYSQL_TEST_HOST` | Database hostname or IP | `127.0.0.1` |
| `MYSQL_TEST_PORT` | Port number | `3306` |
| `MYSQL_TEST_USER` | Database user | `root` |
| `MYSQL_TEST_PASSWORD` | Database password | `password` |
| `MYSQL_TEST_DATABASE` | Default database | `mysql` |

Missing credentials skip the live database tests instead of failing them. Tests live under `tests/` and are not imported by the website catalog.
