#!/usr/bin/env bash

set -uo pipefail

# Site configuration
BACKUP_ROOT="/path/to/oracle/backups"
RETENTION_WINDOW_DAYS=14
ORATAB_PATHS=("/etc/oratab" "/var/opt/oracle/oratab")

usage() {
    printf 'Usage: %s <ORACLE_SID> <level0|level1|archivelog>\n' "${0##*/}" >&2
}

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

if [[ $# -ne 2 ]]; then
    usage
    exit 2
fi

ORACLE_SID=$1
BACKUP_TYPE=$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')

[[ $ORACLE_SID =~ ^[A-Za-z0-9_]+$ ]] ||
    fail "Invalid ORACLE_SID '$ORACLE_SID'. Use only letters, numbers, and underscores."

case $BACKUP_TYPE in
    level0|level1|archivelog) ;;
    *)
        usage
        fail "Unknown backup type '$BACKUP_TYPE'."
        ;;
esac

ORACLE_HOME=""
ORATAB_USED=""

for oratab in "${ORATAB_PATHS[@]}"; do
    [[ -r $oratab ]] || continue

    oracle_home_candidate=$(awk -F: -v sid="$ORACLE_SID" '
        /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
        $1 == sid && $2 != "" { print $2; exit }
    ' "$oratab")

    if [[ -n $oracle_home_candidate ]]; then
        ORACLE_HOME=$oracle_home_candidate
        ORATAB_USED=$oratab
        break
    fi
done

[[ -n $ORACLE_HOME ]] ||
    fail "SID '$ORACLE_SID' was not found in a readable oratab file."
[[ -d $ORACLE_HOME ]] ||
    fail "ORACLE_HOME '$ORACLE_HOME' from '$ORATAB_USED' is not a directory."
[[ -x $ORACLE_HOME/bin/rman ]] ||
    fail "RMAN is not executable at '$ORACLE_HOME/bin/rman'."

export ORACLE_SID ORACLE_HOME
export PATH="$ORACLE_HOME/bin:$PATH"

DATABASE_BACKUP_DIR="$BACKUP_ROOT/$ORACLE_SID"
LOG_DIR="$DATABASE_BACKUP_DIR/logs"

mkdir -p "$DATABASE_BACKUP_DIR" "$LOG_DIR" ||
    fail "Could not create backup directories under '$DATABASE_BACKUP_DIR'."
[[ -w $DATABASE_BACKUP_DIR && -w $LOG_DIR ]] ||
    fail "Backup directories under '$DATABASE_BACKUP_DIR' are not writable."

TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
LOG_FILE="$LOG_DIR/${ORACLE_SID}_${BACKUP_TYPE}_${TIMESTAMP}.log"
PIECE_FORMAT="$DATABASE_BACKUP_DIR/${ORACLE_SID}_${BACKUP_TYPE}_${TIMESTAMP}_%T_%U.bkp"
CONTROLFILE_FORMAT="$DATABASE_BACKUP_DIR/${ORACLE_SID}_${BACKUP_TYPE}_${TIMESTAMP}_controlfile_%T_%U.bkp"

case $BACKUP_TYPE in
    level0)
        BACKUP_COMMAND="BACKUP AS COMPRESSED BACKUPSET INCREMENTAL LEVEL 0 DATABASE FORMAT '$PIECE_FORMAT' TAG 'LEVEL0_BACKUP';"
        ;;
    level1)
        BACKUP_COMMAND="BACKUP AS COMPRESSED BACKUPSET INCREMENTAL LEVEL 1 DATABASE FORMAT '$PIECE_FORMAT' TAG 'LEVEL1_BACKUP';"
        ;;
    archivelog)
        BACKUP_COMMAND="SQL 'ALTER SYSTEM ARCHIVE LOG CURRENT';
BACKUP AS COMPRESSED BACKUPSET ARCHIVELOG ALL DELETE INPUT FORMAT '$PIECE_FORMAT' TAG 'ARCHIVELOG_BACKUP';"
        ;;
esac

printf 'Starting %s backup for SID %s; log: %s\n' \
    "$BACKUP_TYPE" "$ORACLE_SID" "$LOG_FILE"

"$ORACLE_HOME/bin/rman" target / log="$LOG_FILE" <<RMAN
WHENEVER SQLERROR EXIT SQL.SQLCODE;
WHENEVER RMAN ERROR EXIT FAILURE;

CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF $RETENTION_WINDOW_DAYS DAYS;
CROSSCHECK BACKUP;
CROSSCHECK ARCHIVELOG ALL;
DELETE NOPROMPT EXPIRED BACKUP;
DELETE NOPROMPT EXPIRED ARCHIVELOG ALL;

$BACKUP_COMMAND
BACKUP AS COMPRESSED BACKUPSET CURRENT CONTROLFILE
    FORMAT '$CONTROLFILE_FORMAT'
    TAG 'CONTROLFILE_BACKUP';

DELETE NOPROMPT OBSOLETE;
EXIT;
RMAN

rman_status=$?
if (( rman_status != 0 )); then
    printf 'ERROR: RMAN backup failed with status %d. See %s\n' \
        "$rman_status" "$LOG_FILE" >&2
    exit "$rman_status"
fi

printf 'Backup completed successfully. See %s\n' "$LOG_FILE"
