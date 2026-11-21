#!/usr/bin/env bash
# Exercise encryption, remote read-back, and restore using disposable records.
set -euo pipefail
umask 077
stage=$(mktemp -d)
started=false
cleanup() {
  if $started; then pg_ctl -D "$stage/pg" -m fast stop >/dev/null; fi
  rm -rf -- "$stage"
}
trap cleanup EXIT
export PGHOST=127.0.0.1 PGPORT="${DRILL_PORT:-55438}" PGUSER=placeai_drill PGDATABASE=source
unset PGHOSTADDR PGSERVICE PGOPTIONS PGPASSFILE PGPASSWORD
export RCLONE_CONFIG="$stage/rclone.conf"
printf '[fixture]\ntype = local\n' > "$RCLONE_CONFIG"
export BACKUP_REMOTE="fixture:$stage/archive"
initdb -D "$stage/pg" -U "$PGUSER" -E UTF8 --no-locale -A trust >/dev/null
pg_ctl -D "$stage/pg" -l "$stage/server.log" -o "-p $PGPORT -c listen_addresses=127.0.0.1 -c unix_socket_directories=''" start >/dev/null
started=true
createdb source
psql -X -q -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE organizations(id integer PRIMARY KEY);
CREATE TABLE users(id integer PRIMARY KEY, organization_id integer REFERENCES organizations);
CREATE TABLE mock_interviews(id integer PRIMARY KEY, student_id integer REFERENCES users, answer text);
CREATE TABLE assessment_jobs(id integer PRIMARY KEY REFERENCES mock_interviews, state text);
INSERT INTO organizations VALUES (1),(2);
INSERT INTO users VALUES (1,1),(2,2);
INSERT INTO mock_interviews VALUES (1,1,'answer one'),(2,2,'answer two');
INSERT INTO assessment_jobs VALUES (1,'queued'),(2,'complete');
SQL
export BACKUP_IDENTITY="$stage/identity"
age-keygen -o "$BACKUP_IDENTITY"
BACKUP_RECIPIENT=$(age-keygen -y "$BACKUP_IDENTITY")
export BACKUP_RECIPIENT
bash scripts/backup-public-db.sh
archive=("$stage"/archive/*.age)
restored=$(bash scripts/restore-public-drill.sh "${archive[0]}")
query='SELECT o.id,u.id,i.id,i.answer,j.state FROM organizations o JOIN users u ON o.id=u.organization_id JOIN mock_interviews i ON u.id=i.student_id JOIN assessment_jobs j ON i.id=j.id ORDER BY i.id'
psql -XAt -v ON_ERROR_STOP=1 -d source -c "$query" > "$stage/source.rows"
psql -XAt -v ON_ERROR_STOP=1 -d "$restored" -c "$query" > "$stage/restored.rows"
diff -u "$stage/source.rows" "$stage/restored.rows"
head -c 80 "${archive[0]}" > "$stage/truncated.age"
if bash scripts/restore-public-drill.sh "$stage/truncated.age"; then
  echo 'Truncated archive passed verification' >&2; exit 1
fi
echo 'Recovery drill passed for both synthetic tenants.'
