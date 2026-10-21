#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  echo "ملف .env غير موجود؛ أوقف النسخ الاحتياطي." >&2
  exit 1
fi
mkdir -p backups
set -a
source .env
set +a
: "${POSTGRES_USER:?POSTGRES_USER مطلوب في .env}"
: "${POSTGRES_DB:?POSTGRES_DB مطلوب في .env}"
STAMP="$(date +%Y-%m-%d_%H-%M-%S)"
FILE="backups/movements_${STAMP}.dump"
CHECKSUM="${FILE}.sha256"
TMP="$(mktemp "backups/.movements_${STAMP}.XXXXXX.tmp")"
TMP_CHECKSUM="${TMP}.sha256"
cleanup() { rm -f -- "$TMP" "$TMP_CHECKSUM"; }
trap cleanup EXIT

# Custom format supports verification and transactional --clean restores.
docker compose exec -T db pg_dump \
  --format=custom --compress=6 --no-owner --no-acl \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$TMP"
test -s "$TMP"
# Ask pg_restore to inspect the archive before publishing it as a valid backup.
docker compose exec -T db pg_restore --list < "$TMP" >/dev/null
sha256sum "$TMP" | awk -v file="$FILE" '{print $1 "  " file}' > "$TMP_CHECKSUM"
mv -- "$TMP" "$FILE"
mv -- "$TMP_CHECKSUM" "$CHECKSUM"

# Keep the 14 newest completed custom backups and their checksum files.
mapfile -t OLD_FILES < <(find backups -maxdepth 1 -type f -name 'movements_*.dump' -printf '%T@ %p\n' | sort -nr | awk 'NR>14 {$1=""; sub(/^ /, ""); print}')
for old in "${OLD_FILES[@]}"; do
  rm -f -- "$old" "${old}.sha256"
done
printf 'تم إنشاء نسخة احتياطية والتحقق منها: %s\n' "$FILE"
printf 'البصمة: %s\n' "$CHECKSUM"
