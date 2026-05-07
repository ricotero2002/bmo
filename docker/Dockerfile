# ==============================================================
# Dockerfile Multi-Stage Altamente Optimizado
# ==============================================================
# Etapas:
#   builder       -> Instala deps con compiladores
#   final-api     -> Imagen de produccion: FastAPI (Non-root)
#   final-worker  -> Imagen de produccion: Celery Worker (Non-root)
#   local         -> Imagen local: API + testing + flower
# ==============================================================

# Stage 1: Builder
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements/ ./requirements/

# Instalar dependencias en /install
RUN pip install --upgrade pip && \
    pip install --prefix=/install -r requirements/prod.txt

# Stage 2: Builder LOCAL
FROM builder AS builder-local
RUN pip install --prefix=/install -r requirements/local.txt

# Stage 3: BASE FINAL
FROM python:3.12-slim AS base-final

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    OPENSSL_CONF=/app/docker/openssl/openssl.cnf \
    OPENSSL_MODULES=/usr/lib/x86_64-linux-gnu/ossl-modules \
    KAFKA_SSL_PROVIDER=legacy

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    openssl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no privilegiado para seguridad
RUN groupadd -r appuser && useradd -r -g appuser -s /sbin/nologin appuser

COPY --from=builder /install /usr/local
COPY docker/openssl/ /app/docker/openssl/

WORKDIR /app
COPY src/ ./src/
RUN mkdir -p logs && chown -R appuser:appuser /app

# Stage 4: FINAL-API
FROM base-final AS final-api
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1
CMD ["gunicorn", "src.api.main:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]

# Stage 5: FINAL-WORKER
FROM base-final AS final-worker
USER appuser
CMD ["celery", "-A", "src.workers.celery_app", "worker", \
     "--loglevel=info", \
     "--concurrency=2", \
     "--max-tasks-per-child=100", \
     "--prefetch-multiplier=1"]

# Stage 6: LOCAL
FROM python:3.12-slim AS local
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    OPENSSL_CONF=/app/docker/openssl/openssl.cnf \
    OPENSSL_MODULES=/usr/lib/x86_64-linux-gnu/ossl-modules \
    KAFKA_SSL_PROVIDER=legacy

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    openssl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder-local /install /usr/local
COPY docker/openssl/ /app/docker/openssl/

WORKDIR /app
COPY src/ ./src/
RUN mkdir -p logs

EXPOSE 8000
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]