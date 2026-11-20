#!/usr/bin/env bash
# Publish an encrypted logical backup of the PlaceAI application schema.
set -euo pipefail
umask 077
: "${PGDATABASE:?Set the source database name using libpq settings}"
: "${BACKUP_RECIPIENT:?Set the recovery age public key}"
: "${BACKUP_REMOTE:?Set the approved rclone remote and directory}"
[[ $BACKUP_REMOTE =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*: ]] || { echo 'Expected a configured rclone remote' >&2; exit 2; }
[[ $BACKUP_RECIPIENT == age1* ]] || { echo 'An age public key is required' >&2; exit 2; }

stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
name="placeai-public-$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import uuid; print(uuid.uuid4().hex)').dump.age"
target="${BACKUP_REMOTE%/}/$name"
pg_dump --no-password --schema=public --format=custom --no-owner --no-privileges |
  age --encrypt --recipient "$BACKUP_RECIPIENT" --output "$stage/$name"

rclone copyto --immutable "$stage/$name" "$target"
expected=$(sha256sum < "$stage/$name")
received=$(rclone cat "$target" | sha256sum)
[[ $received == "$expected" ]] || { echo 'Uploaded backup checksum mismatch' >&2; exit 1; }
echo "Verified encrypted archive: $name"
