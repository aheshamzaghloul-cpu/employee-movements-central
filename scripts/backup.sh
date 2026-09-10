#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
set -a
source .env
set +a
STAMP="$(date +%Y-%m-%d_%H-%M-%S)"
FILE="backups/movements_${STAMP}.sql.gz"
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$FILE"
# الاحتفاظ بآخر 14 نسخة فقط
ls -1t backups/movements_*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
printf 'تم إنشاء النسخة الاحتياطية: %s\n' "$FILE"
