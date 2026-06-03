# ---------- Builder ----------
FROM python:3.11-slim AS builder

# CPU-only torch: ~200 MB вместо ~2 GB
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

# ---------- Runtime ----------
FROM python:3.11-slim AS runtime

# Зависимости Pillow/libGL для YOLO
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем torch из builder, ставим остальное из PyPI
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Сначала манифест — лучше кэшируется слой
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
        "fastapi>=0.115" \
        "uvicorn[standard]>=0.32" \
        "pydantic>=2.9" \
        "pydantic-settings>=2.6" \
        "python-multipart>=0.0.20" \
        "Pillow>=11.0" \
        "httpx>=0.27" \
        "ultralytics>=8.3"

# Код
COPY app ./app

# Непривилегированный пользователь
RUN useradd -m -u 10001 cvuser
USER cvuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
