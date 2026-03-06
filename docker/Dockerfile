# Etapa 1: Constructor
FROM python:3.12-slim as builder
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc python3-dev
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Etapa 2: Ejecución
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH
EXPOSE 8000

# Usar exec form para que las señales de sistema (lifespan) se procesen bien
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]