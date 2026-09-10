#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$#" -ne 1 ]; then
  echo "الاستخدام: ./scripts/restore.sh backups/movements_YYYY-MM-DD_HH-MM-SS.sql.gz"
  exit 1
fi
FILE="$1"
if [ ! -f "$FILE" ]; then echo "ملف النسخة الاحتياطية غير موجود: $FILE"; exit 1; fi
set -a
source .env
set +a
echo "تحذير: الاستعادة ستستبدل بيانات قاعدة البيانات الحالية."
read -r -p "اكتب RESTORE للتأكيد: " CONFIRM
[ "$CONFIRM" = "RESTORE" ] || { echo "تم الإلغاء."; exit 1; }
gzip -dc "$FILE" | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
echo "اكتملت الاستعادة."
