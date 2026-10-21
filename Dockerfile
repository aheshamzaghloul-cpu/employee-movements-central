FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
# Local-only OCR for ServiceDesk ticket screenshots (Arabic and English labels).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8000'), timeout=4)"

# --preload runs the database bootstrap once in the master process before workers fork.
CMD ["sh", "-c", "exec gunicorn --config gunicorn.conf.py --preload -w ${WEB_CONCURRENCY:-3} -b 0.0.0.0:${PORT:-8000} --timeout 60 --access-logfile - wsgi:app"]
