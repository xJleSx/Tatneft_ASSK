# syntax=docker/dockerfile:1.7
# ---- Stage 1: builder ----
# Собираем wheel-файлы для проекта и всех зависимостей.
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --upgrade pip && \
    pip wheel --wheel-dir=/wheels .

# ---- Stage 2: runtime ----
# Минимальный образ: только рантайм-зависимости, non-root user, healthcheck.
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Системный пользователь без root-прав
RUN groupadd --system --gid 1001 appgroup && \
    useradd  --system --uid 1001 --gid appgroup \
             --home /app --shell /bin/bash appuser

# Только рантайм-библиотеки (без компиляторов)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установка из локальных wheels (без сети, без кеша pip)
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels askk-backend \
    && rm -rf /wheels

# Код и миграции
COPY --from=builder /build/alembic     ./alembic
COPY --from=builder /build/alembic.ini ./alembic.ini
COPY --from=builder /build/app         ./app

# Каталог для фото и владелец
RUN mkdir -p /app/photos_storage \
    && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

# Healthcheck без curl/wget: проверяем, что порт 8000 слушается
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1', 8000)); s.close()" || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
