#!/usr/bin/env sh
# Nightly PostgreSQL backup. Usage: DATABASE_URL=postgres://... BACKUP_DIR=/backups ./scripts/backup_db.sh
set -eu
BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date +%F-%H%M)"
pg_dump --format=custom --no-owner "$DATABASE_URL" > "$BACKUP_DIR/kampusdey-$STAMP.dump"
# Keep 14 days locally; copy off-site with your storage tool of choice.
find "$BACKUP_DIR" -name 'kampusdey-*.dump' -mtime +14 -delete
echo "Backup written to $BACKUP_DIR/kampusdey-$STAMP.dump"
