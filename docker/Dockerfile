# ==============================================================
# Dockerfile Multi-Stage Optimizado
# ==============================================================
# Etapas:
#   builder       -> Instala deps con compiladores (descartado)
#   final-api     -> Imagen de produccion: FastAPI
#   final-worker  -> Imagen de produccion: Celery Worker
#   local         -> Imagen local: API + testing + flower
# ==============================================================

# ==============================================================
# Stage 1: Builder - Compila e instala todas las dependencias
# Esta etapa se descarta al final, no va a la imagen final.
# ==============================================================
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Herramientas de compilacion (solo necesarias para compilar C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar solo requirements para aprovechar cache de capas
COPY requirements/ ./requirements/

# Instalar dependencias de PRODUCCION en un directorio especial
RUN pip install --upgrade pip && \
    pip install --prefix=/install -r requirements/prod.txt


# ==============================================================
# Stage 2: Builder LOCAL - Agrega herramientas de testing
# ==============================================================
FROM builder AS builder-local

RUN pip install --prefix=/install -r requirements/local.txt


# ==============================================================
# Stage 3: BASE FINAL - Imagen limpia sin compiladores
# ==============================================================
FROM python:3.12-slim AS base-final

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Solo curl para healthchecks (sin gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependencias ya compiladas del builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copiar codigo fuente
COPY src/ ./src/

# Crear directorio de logs
RUN mkdir -p logs


# ==============================================================
# Stage 4: FINAL-API - Imagen de produccion para la API
# Build: docker build --target final-api -t personal_ai_api:latest -f docker/Dockerfile .
# ==============================================================
FROM base-final AS final-api

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]


# ==============================================================
# Stage 5: FINAL-WORKER - Imagen de produccion para Celery
# Build: docker build --target final-worker -t personal_ai_worker:latest -f docker/Dockerfile .
# ==============================================================
FROM base-final AS final-worker

CMD ["celery", "-A", "src.workers.celery_app", "worker", \
     "--loglevel=info", \
     "--concurrency=2", \
     "--max-tasks-per-child=100", \
     "--prefetch-multiplier=1"]


# ==============================================================
# Stage 6: LOCAL - Imagen de desarrollo (con testing + flower)
# Build: docker build --target local -t personal_ai_api:local -f docker/Dockerfile .
# ==============================================================
FROM python:3.12-slim AS local

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependencias de local (incluye testing y flower)
COPY --from=builder-local /install /usr/local

WORKDIR /app
COPY src/ ./src/
RUN mkdir -p logs

EXPOSE 8000
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]