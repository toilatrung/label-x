#!/bin/sh
set -eu
umask 077
# Fail once before allocating dumps when the shared disk is already under pressure.
free_kib=$(df -Pk /backups | awk 'NR==2 {print $4}')
[ "$free_kib" -ge 8388608 ] || { echo 'BLOCKED backup disk has less than 8 GiB free'; exit 1; }
trap 'touch /work/failed' EXIT
# Every GitOps revision recreates the datastore pods, and a new job pod can be refused by the
# namespace network policy until it is programmed: wait for PostgreSQL instead of failing the
# whole sync on the first refused connection (the job has backoffLimit 0).
attempt=0
until pg_isready --quiet --timeout=2; do
  attempt=$((attempt + 1))
  [ "$attempt" -lt 90 ] || { echo 'BLOCKED PostgreSQL did not accept connections within 3 minutes'; exit 1; }
  sleep 2
done
backup_id="$(date -u +%Y%m%dT%H%M%SZ)-${POD_NAME}"
printf '%s' "$backup_id" > /work/id
pg_dump --format=custom --no-owner --no-privileges --file=/work/database.dump
pg_restore --list /work/database.dump > /work/contents.txt
touch /work/dumped
# The uploader verifies the remote encrypted dump and returns a decrypted copy.
attempt=0
while [ ! -f /work/verified ]; do
  [ ! -f /work/upload-failed ] || exit 1
  attempt=$((attempt + 1))
  [ "$attempt" -lt 1800 ] || exit 1
  sleep 2
done
# Restore only to a new disposable database in the same PostgreSQL instance.
restore_db="labelx_restorecheck_$(printf '%s' "$POD_NAME" | sha256sum | cut -c1-12)_$(date +%s)"
createdb "$restore_db"
trap 'dropdb --if-exists "$restore_db"; touch /work/failed' EXIT
pg_restore --exit-on-error --no-owner --no-privileges --dbname="$restore_db" /work/roundtrip.dump
psql --dbname="$restore_db" --no-psqlrc -v ON_ERROR_STOP=1 -c 'SELECT count(*) AS restored_tables FROM information_schema.tables WHERE table_schema = '\''public'\'';' > /work/restore-check.txt
dropdb "$restore_db"
cp /work/database.dump.enc "/backups/${backup_id}.dump.enc"
cp /work/receipt.json "/backups/${backup_id}.json"
touch /work/restored
trap - EXIT
echo 'PASS encrypted backup round-trip and disposable database restore; check receipt location, offsite remains unverified'
