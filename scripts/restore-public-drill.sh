#!/usr/bin/env bash
# Restore one trusted backup into a newly created database on a local drill server.
set -euo pipefail
umask 077
: "${1:?Supply the path of a downloaded encrypted archive}"
[[ -f $1 ]] || { echo 'Archive missing' >&2; exit 2; }
unset PGSERVICE PGHOSTADDR PGOPTIONS PGDATABASE
export PGHOST=127.0.0.1
db="placeai_drill_$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
: "${BACKUP_IDENTITY:?Set the path to the age recovery identity}"
age --decrypt --identity "$BACKUP_IDENTITY" --output "$stage/public.dump" < "$1"
pg_restore --list "$stage/public.dump" > "$stage/contents"
createdb --no-password --template=template0 "$db"
echo "Isolated restore database: $db" >&2
if grep -Eq ' SCHEMA - public( |$)' "$stage/contents"; then
  psql --no-password -X -q -v ON_ERROR_STOP=1 -d "$db" -c 'DROP SCHEMA public RESTRICT' >&2
fi
pg_restore --no-password --single-transaction --exit-on-error --no-owner --no-privileges --dbname="$db" "$stage/public.dump"
psql --no-password -X -v ON_ERROR_STOP=1 -d "$db" -c 'SELECT (SELECT count(*) FROM public.organizations) AS organizations, (SELECT count(*) FROM public.users) AS users, (SELECT count(*) FROM public.mock_interviews) AS interviews, (SELECT count(*) FROM public.assessment_jobs) AS assessment_jobs' >&2
echo "$db"
