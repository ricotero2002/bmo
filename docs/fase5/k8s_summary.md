# K8s Migration & Docker Optimization — Estado y Comandos

## ¿Qué se hizo?

### 1. Separación de Dependencias por Entorno
Se creó la carpeta `requirements/` con tres archivos:

| Archivo | Qué incluye | Tamaño de imagen esperado |
|---|---|---|
| `base.txt` | LangChain, Celery, DB, Redis, Storage | (compartido) |
| `prod.txt` | `base` + FastAPI, Uvicorn, Markitdown | ~700 MB |
| `local.txt` | `prod` + Pytest, Flower, deepeval, testcontainers | ~1.1 GB |

### 2. Dockerfile Multi-Stage

| Stage | Propósito | Imagen resultante |
|---|---|---|
| `builder` | Compila deps con gcc/g++ (se **descarta**) | — |
| `builder-local` | Agrega deps de testing (se **descarta**) | — |
| `final-api` | Producción: FastAPI | `personal_ai_api:latest` (~700MB) |
| `final-worker` | Producción: Celery Worker | `personal_ai_worker:latest` (~650MB) |
| `local` | Local/Dev: API + tests + hot-reload | `personal_ai_api:local` (~1.1GB) |

### 3. Archivos actualizados
- `.dockerignore` — Excluye `.git`, `docs/`, `frontend/`, logs, y secretos.
- `k8s/apps-deployment.yaml` — Worker ahora usa `personal_ai_worker:latest`.

---

## Comandos a ejecutar (en este orden)

### PASO 1: Construir las imágenes

```powershell
# Imagen de API (produccion)
docker build --target final-api -t personal_ai_api:latest -f docker/Dockerfile .

# Imagen de Worker (produccion)
docker build --target final-worker -t personal_ai_worker:latest -f docker/Dockerfile .

# Imagen local (desarrollo, con tests y hot-reload)
docker build --target local -t personal_ai_api:local -f docker/Dockerfile .
```

### PASO 2: Verificar tamaños

```powershell
docker images | Select-String "personal_ai"
```

### PASO 3: Importar al clúster k3d

```powershell
k3d image import personal_ai_api:latest    -c mycluster
k3d image import personal_ai_worker:latest  -c mycluster
```

kubectl create secret generic infisical-auth-secret `
  --from-literal=clientId="TU_CLIENT_ID_REAL" `
  --from-literal=clientSecret="TU_CLIENT_SECRET_REAL" `
  --namespace personal-ai `
  --dry-run=client -o yaml | kubectl apply -f -


### PASO 4: Aplicar manifiestos de Kubernetes

```powershell
# ConfigMap (variables no secretas)
kubectl apply -f k8s/app-configmap.yaml

# Infisical (sincronizacion de secretos)
kubectl apply -f k8s/infisical-config.yaml

# Deployments (API + Worker) y Servicios
kubectl apply -f k8s/apps-deployment.yaml

# KEDA Scaler (auto-escalado basado en RabbitMQ)
kubectl apply -f k8s/keda-scaler.yaml
```

si ya estan hay que reimportar:

docker build --target final-api -t personal_ai_api:latest -f docker/Dockerfile .
docker build --target final-worker -t personal_ai_worker:latest -f docker/Dockerfile .
docker build -t personal_ai_airflow:latest -f data_tooling/airflow/Dockerfile .
docker build -f docker/spark/Dockerfile.spark-connect -t personal_ai_spark_connect:latest .



k3d image import personal_ai_api:latest -c mycluster
k3d image import personal_ai_worker:latest -c mycluster
k3d image import personal_ai_airflow:latest -c mycluster
k3d image import personal_ai_spark_connect:latest -c mycluster


k3d image import personal_ai_api:latest personal_ai_worker:latest -c mycluster



kubectl rollout restart deployment -n personal-ai

kubectl rollout restart deployment/api-deployment -n personal-ai

kubectl rollout restart deployment otel-collector-opentelemetry-collector -n observability


helm upgrade --install otel-collector open-telemetry/opentelemetry-collector -f k8s/otel-collector-values.yaml -n observability

### PASO 5: Verificar pods

```powershell
# Esperar a que arranquen (Ctrl+C para salir)
kubectl get pods -n personal-ai -w

# Ver logs de la API
kubectl logs -n personal-ai -l app=api --follow
kubectl logs -n personal-ai -l app=iceberg-rest --follow
kubectl logs -n personal-ai -l app=spark-thrift --follow
kubectl logs -n personal-ai -l app=bmo-airflow-worker --follow
kubectl logs -n personal-ai -l app=bmo-airflow-webserver --follow


helm upgrade --install bmo-airflow https://github.com/apache/airflow/releases/download/helm-chart-1.16.0/airflow-1.16.0.tgz --namespace personal-ai -f k8s/airflow/helm-values.yaml

helm install bmo-airflow apache-airflow/airflow -n personal-ai -f k8s/airflow/helm-values.yaml --timeout 10m
# Ver logs del Worker
kubectl logs -n personal-ai -l app=worker --follow
```
kubectl get pods -n observability -w



### PASO 6: Verificar acceso a la API

```powershell
# La API debería estar en http://localhost:8081
curl http://localhost:8081/api/health
```

---

## Comandos de troubleshooting

```powershell
# Ver qué impide que un pod arranque
kubectl describe pod -n personal-ai <nombre-del-pod>

# Ver estado del auto-escalado de KEDA
kubectl get scaledobject -n personal-ai

kubectl logs keda-operator-687fb5779d-9lbnz -n keda | findstr kafka-consumer-scaler

# Verificar secretos sincronizados por Infisical
kubectl get secrets -n personal-ai

# Reiniciar un deployment sin borrar pods
kubectl rollout restart deployment/api-deployment -n personal-ai
kubectl rollout restart deployment/worker-deployment -n personal-ai

# Estado del clúster
kubectl get all -n personal-ai

kubectl delete rs -n personal-ai $(kubectl get rs -n personal-ai -o jsonpath='{.items[?(@.spec.replicas==0)].metadata.name}')

# Ver recursos del nodo
kubectl top nodes
kubectl top pods -n personal-ai

kubectl logs -n infisical-operator -l control-plane=controller-manager --tail=100

kubectl describe pod -n personal-ai -l app=api

kubectl get configmap app-config -n personal-ai -o yaml

kubectl get configmap app-config -n personal-ai -o json
```

---

## Notas importantes

> [!IMPORTANT]
> Después de cada `docker build`, debes volver a ejecutar `k3d image import` para que el clúster use la nueva versión de la imagen. K8s no la actualiza sola.

> [!NOTE]
> Infisical necesita que configures el `InfisicalSecret` de autenticación. Tendrás que crear un secret manualmente con tus credenciales antes de que `k8s/infisical-config.yaml` funcione.

---

## Acceder a la API desde el browser (reemplaza localhost:8000)

Con k3d, la API ya **no está en** `localhost:8000` — está expuesta via Ingress en el puerto `8081`.

```powershell
# Swagger UI (equivalente al /docs de antes)
Start-Process "http://localhost:8081/docs"

# Health check
curl http://localhost:8081/api/health
```

> [!IMPORTANT]
> El puerto `8081` es el que se mapeó al crear el cluster: `k3d cluster create mycluster -p "8081:80@loadbalancer"`.
> Si ves **502 Bad Gateway**, el pod todavía está iniciando. Revisá con `kubectl get pods -n personal-ai -w`.

---

## Auto-scaling de la API por CPU

El worker ya escala con KEDA (colas de RabbitMQ). Para escalar la **API**, se usa un `HorizontalPodAutoscaler` (HPA) nativo de Kubernetes. El archivo `k8s/api-hpa.yaml` ya está creado.

**Requisito previo:** el Deployment necesita `resources.requests.cpu` definido:

```powershell
# Parchear el deployment con limits de CPU (temporal, para prueba)
kubectl set resources deployment api-deployment -n personal-ai `
  --requests=cpu=100m --limits=cpu=500m

# Aplicar el HPA
kubectl apply -f k8s/api-hpa.yaml
```

> [!IMPORTANT]
> Para que quede permanente, agregar `resources:` en `apps-deployment.yaml` dentro del container `api`:
> ```yaml
> resources:
>   requests:
>     cpu: "100m"
>   limits:
>     cpu: "500m"
> ```

**Monitoreo del HPA:**
```powershell
# Estado: réplicas actuales y % CPU
kubectl get hpa -n personal-ai

# Detalles y eventos de escalado
kubectl describe hpa api-hpa -n personal-ai
```

---

## Monitoreo

### Comandos esenciales

```powershell
# Pods en tiempo real
kubectl get pods -n personal-ai -w

# Consumo de CPU y RAM por pod
kubectl top pods -n personal-ai

# Estado del HPA (CPU)
kubectl get hpa -n personal-ai

# Estado de KEDA (RabbitMQ)
kubectl get scaledobject -n personal-ai

# Eventos del cluster (errores, escalados, crashs)
kubectl get events -n personal-ai --sort-by=.lastTimestamp

# Logs de API y Worker
kubectl logs -n personal-ai -l app=api --follow
kubectl logs -n personal-ai -l app=worker --follow

kubectl get pods -n observability; 
kubectl logs -n observability -l app.kubernetes.io/name=opentelemetry-collector --tail=20

kubectl describe pod -n observability -l app.kubernetes.io/name=opentelemetry-collector

```

### k9s — Dashboard de terminal (recomendado)

```powershell
choco install k9s  # Una sola vez

k9s --namespace personal-ai
```

| Tecla | Acción |
|---|---|
| `:pod` | Ver pods |
| `:hpa` | Ver HPAs |
| `:scaledobject` | Ver KEDA |
| `l` | Logs del pod seleccionado |
| `d` | Describe el recurso |

---

## OpenTelemetry + Grafana Cloud

Integración para tener **trazas distribuidas y métricas** de FastAPI y Celery en Grafana Cloud.

### Paso 1: Credenciales de Grafana Cloud

1. Registrarse en [grafana.com](https://grafana.com) (hay free tier)
2. Ir a **My Account → Stack → OpenTelemetry**
3. Copiar el `OTLP Endpoint` y el `Authorization Header`

```powershell
kubectl create secret generic grafana-otel-secret `
  --from-literal=endpoint="https://otlp-gateway-prod-us-east-0.grafana.net/otlp" `
  --from-literal=auth="Basic TU_TOKEN_BASE64" `
  --namespace observability
```

### Paso 2: Instalar OpenTelemetry Collector via Helm

```powershell
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update

helm upgrade --install otel-collector open-telemetry/opentelemetry-collector `
  --namespace observability --create-namespace `
  -f k8s/prod/otel-collector-values.yaml'

helm upgrade --install otel-collector open-telemetry/opentelemetry-collector -f k8s/otel-collector-values.yaml -n observability

kubectl delete pod -l app.kubernetes.io/name=opentelemetry-collector -n observability

kubectl get pods -n observability -w
```

Crear `k8s/otel-collector-values.yaml`:

```yaml
mode: deployment
config:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318
  exporters:
    otlphttp:
      endpoint: "${GRAFANA_OTLP_ENDPOINT}"
      headers:
        Authorization: "${GRAFANA_OTLP_AUTH}"
  service:
    pipelines:
      traces:
        receivers: [otlp]
        exporters: [otlphttp]
      metrics:
        receivers: [otlp]
        exporters: [otlphttp]
```

### Paso 3: Instrumentar FastAPI y Celery

Dependencias:

```bash
pip install opentelemetry-sdk \
            opentelemetry-exporter-otlp-proto-grpc \
            opentelemetry-instrumentation-fastapi \
            opentelemetry-instrumentation-celery

pip install opentelemetry-distro
pip install opentelemetry-exporter-otlp
opentelemetry-bootstrap --action=install
```

En `src/api/main.py`:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
    endpoint="http://otel-collector.observability.svc.cluster.local:4317",
    insecure=True
)))
trace.set_tracer_provider(provider)
FastAPIInstrumentor.instrument_app(app)
```

En el worker Celery:

```python
from opentelemetry.instrumentation.celery import CeleryInstrumentor
CeleryInstrumentor().instrument()
```

Variables de entorno para agregar en `apps-deployment.yaml`:

```yaml
env:
  - name: OTEL_SERVICE_NAME
    value: "personal-ai-api"   # o "personal-ai-worker" en el worker
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: "http://otel-collector.observability.svc.cluster.local:4317"
```

### Paso 4: Ver trazas en Grafana Cloud

1. Ir al stack de Grafana → **Explore**
2. Fuente: **Tempo** (trazas) → buscar por `service.name = "personal-ai-api"`
3. Fuente: **Prometheus** → métricas como `http_server_requests_total`

> [!TIP]
> Importar el dashboard ID `17175` en Grafana para tener métricas pre-armadas de FastAPI.




1. Tráfico de tu API (Tasa de Peticiones)
Métrica a usar: http_server_duration_milliseconds_count

¿Para qué sirve? Te dice cuántas peticiones está recibiendo tu API (por ejemplo, cuánta gente está enviando documentos al mismo tiempo).

Cómo graficarlo (PromQL): Para ver las Peticiones por Segundo (RPS) agrupadas por endpoint (ruta):

Code snippet
sum by (http_route) (rate(http_server_duration_milliseconds_count[5m]))
Visualización recomendada en Grafana: Time series.

2. Latencia de tu API (¿Qué tan rápida es?)
Métrica a usar: http_server_duration_milliseconds_sum y _count

¿Para qué sirve? Te muestra cuánto tardan tus endpoints en responder. Si el endpoint /ask de repente salta de 5 segundos a 30 segundos, este gráfico te lo mostrará de inmediato.

Cómo graficarlo (PromQL): Para calcular el tiempo de respuesta promedio en milisegundos:

Code snippet
sum(rate(http_server_duration_milliseconds_sum[5m])) / sum(rate(http_server_duration_milliseconds_count[5m]))
Visualización recomendada en Grafana: Time series o Stat.

3. Peticiones Activas (Cuellos de botella)
Métrica a usar: http_server_active_requests

¿Para qué sirve? Es un indicador en tiempo real de cuántas peticiones se están procesando en este preciso instante. Si este número sube y no baja, significa que tu API se quedó "trabada" (por ejemplo, la base de datos no responde).

Cómo graficarlo (PromQL):

Code snippet
sum(http_server_active_requests)
Visualización recomendada en Grafana: Stat (un número grande) o Gauge (un velocímetro).

4. Rendimiento de los Workers de Celery (Flower)
Métrica a usar: flower_task_runtime_seconds_sum y _count

¿Para qué sirve? Te dice si tus tareas en segundo plano (como el procesamiento de documentos pesados) están tardando demasiado o están fluyendo bien.

Cómo graficarlo (PromQL): Para ver el tiempo promedio de ejecución de tus tareas de Celery en segundos:

Code snippet
rate(flower_task_runtime_seconds_sum[5m]) / rate(flower_task_runtime_seconds_count[5m])
¿Cómo convierto esto en un Dashboard hermoso?
Para dejar de ver listas aburridas y pasar a los gráficos, sigue estos pasos en Grafana Cloud:

En el menú de la izquierda, haz clic en el ícono de "+" (Create) y selecciona New Dashboard.

Haz clic en + Add visualization.

Selecciona tu base de datos de Prometheus (usualmente llamada grafanacloud-tunombre-prom).

En la parte inferior, verás un campo llamado "Metrics browser" o un botón que dice "Code". Haz clic en "Code" para poder escribir directamente.

Pega una de las consultas de PromQL que te dejé arriba (por ejemplo, la de latencia).

Haz clic en el botón azul "Run queries" (arriba a la derecha).

En el panel derecho, bajo "Title", ponle un nombre (ej. "Tiempo Medio de Respuesta API").

Arriba a la derecha, haz clic en "Apply".

¡Repite esto 4 veces con las consultas de arriba y tendrás un Dashboard de salud completo de tu sistema BMO!



kubectl apply -f k8s/kafka-deployment.yaml

kubectl delete scaledobject kafka-consumer-scaler -n personal-ai; kubectl get scaledobject -n personal-ai

kubectl delete statefulset bmo-airflow-worker-0  -n personal-ai
kubectl delete deployment spark-connect  -n personal-ai


kubectl rollout restart deployment kafka-consumer-deployment -n personal-ai
kubectl rollout restart deployment api-deployment -n personal-ai
kubectl rollout restart deployment worker-deployment -n personal-ai

Acordarme los secretos de infisical, y el de ca de kafka.

kubectl create secret generic kafka-ca-cert \
  --from-file=ca.pem=./ca.pem \
  -n personal-ai


kubectl create secret generic infisical-auth-secret `
  --from-literal=clientId="TU_CLIENT_ID_REAL" `
  --from-literal=clientSecret="TU_CLIENT_SECRET_REAL" `
  --namespace personal-ai `
  --dry-run=client -o yaml | kubectl apply -f -