FROM python:3.13-slim

LABEL org.opencontainers.image.title="Third Opinion Routing"
LABEL org.opencontainers.image.version="1.4.0"
LABEL org.opencontainers.image.description="Offline clinical routing hackathon prototype"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/storage/third_opinion.sqlite3

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/app /app/backend/app
COPY frontend /app/frontend
COPY data/demo /app/data/demo
COPY VERSION /app/VERSION

RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup appuser \
    && mkdir -p /app/storage \
    && chown -R appuser:appgroup /app

USER appuser
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD python -c "import os, urllib.request; port=os.getenv('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=2)" || exit 1

CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
