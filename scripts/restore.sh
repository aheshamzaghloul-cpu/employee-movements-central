#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
if [ "$#" -ne 1 ]; then
  echo "الاستخدام: ./scripts/restore.sh backups/movements_YYYY-MM-DD_HH-MM-SS.dump" >&2
  echo "يمكن أيضًا قراءة نسخ SQL.gz القديمة، لكنها لا تضمن استبدال المخطط القديم بالكامل." >&2
  exit 1
fi
FILE="$1"
if [ ! -f "$FILE" ]; then echo "ملف النسخة الاحتياطية غير موجود: $FILE" >&2; exit 1; fi
if [ ! -f .env ]; then echo "ملف .env غير موجود؛ أوقف الاستعادة." >&2; exit 1; fi
set -a
source .env
set +a
: "${POSTGRES_USER:?POSTGRES_USER مطلوب في .env}"
: "${POSTGRES_DB:?POSTGRES_DB مطلوب في .env}"

case "$FILE" in
  *.dump)
    if [ -f "${FILE}.sha256" ]; then
      if ! sha256sum --check --status "${FILE}.sha256"; then
        echo "فشل التحقق من SHA-256؛ لن تبدأ الاستعادة." >&2
        exit 1
      fi
    else
      echo "تحذير: ملف البصمة غير موجود؛ لن يمكن التحقق من سلامة المصدر." >&2
      read -r -p "اكتب RESTORE_WITHOUT_CHECKSUM للمتابعة: " CONFIRM_HASH
      [ "$CONFIRM_HASH" = "RESTORE_WITHOUT_CHECKSUM" ] || { echo "تم الإلغاء."; exit 1; }
    fi
    # Structural validation is performed before any data is changed.
    docker compose exec -T db pg_restore --list < "$FILE" >/dev/null
    echo "تحذير: ستُستبدل كائنات وبيانات المخطط المستهدفة بمحتوى النسخة الاحتياطية." >&2
    read -r -p "اكتب RESTORE للتأكيد: " CONFIRM
    [ "$CONFIRM" = "RESTORE" ] || { echo "تم الإلغاء."; exit 1; }
    # A single transaction means a failed restore rolls back instead of leaving a partial database.
    docker compose exec -T db pg_restore --clean --if-exists --single-transaction --no-owner --no-acl \
      -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$FILE"
    ;;
  *.sql.gz)
    gzip -t -- "$FILE"
    echo "تحذير: هذه نسخة SQL قديمة. يجب استعادتها إلى قاعدة فارغة أو معزولة؛ لا يمكن ضمان استبدال كامل المخطط الحالي." >&2
    read -r -p "اكتب RESTORE_LEGACY_SQL للتأكيد: " CONFIRM
    [ "$CONFIRM" = "RESTORE_LEGACY_SQL" ] || { echo "تم الإلغاء."; exit 1; }
    gzip -dc -- "$FILE" | docker compose exec -T db psql -X --single-transaction -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
    ;;
  *)
    echo "صيغة غير مدعومة. استخدم ملف .dump جديدًا أو نسخة .sql.gz قديمة." >&2
    exit 1
    ;;
esac
printf 'اكتملت الاستعادة بنجاح. اختبر /healthz وسجّل الدخول وتحقق من أعداد السجلات قبل إعادة فتح الخدمة.\n'
