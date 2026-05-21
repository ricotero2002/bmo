# Arquitectura de Despliegue por Perfiles — BMO Cluster

> **Objetivo:** Poder levantar/bajar selectivamente Airflow, Metabase y el stack de datos sin tocar la API principal. Dos vías: terminal (Skaffold) o visual (Tilt).

---

## Estructura de Archivos Creados

```
personal-ai-assistant/
│
├── skaffold.yaml                     ← Orquestador CLI (build + deploy)
├── Tiltfile                          ← Panel web visual (localhost:10350)
│
└── helm/
    ├── 1-base-stack/                 ← SIEMPRE encendido
    │   ├── Chart.yaml
    │   ├── values.yaml
    │   └── templates/
    │       ├── 00-namespace.yaml
    │       ├── 01-infisical-config.yaml
    │       ├── 02-app-configmap.yaml
    │       ├── 03-traefik-middlewares.yaml
    │       ├── 04-apps-deployment.yaml   ← API + Worker + Celery Exporter
    │       ├── 05-keda-scalers.yaml      ← HPA + KEDA ScaledObjects
    │       └── 06-otel-rbac.yaml
    │
    ├── 2-data-stack/                 ← ETL (opcional)
    │   ├── Chart.yaml                ← Declara Airflow como dependencia
    │   ├── values.yaml               ← Toda la config de Airflow
    │   └── templates/
    │       ├── 01-iceberg-rest.yaml
    │       ├── 02-spark-connect.yaml
    │       └── 03-init-iceberg-namespaces.yaml
    │
    └── 3-analytics-stack/            ← BI (opcional)
        ├── Chart.yaml                ← Declara Trino como dependencia
        ├── values.yaml               ← Config de Trino + catálogo Iceberg
        └── templates/
            └── 01-metabase.yaml
```

---

## Qué va en cada stack

| Stack | Componente | Tipo |
|-------|-----------|------|
| **Base** | API FastAPI (`personal_ai_api`) | Deployment propio |
| **Base** | Worker Celery (`personal_ai_worker`) | Deployment propio |
| **Base** | Celery Exporter | Deployment externo |
| **Base** | Infisical Operator | CRD externo |
| **Base** | KEDA ScaledObjects + HPA | CRDs del cluster |
| **Base** | Traefik Middlewares | CRDs del cluster |
| **Base** | OpenTelemetry Collector | Sub-chart Helm |
| **Data** | Airflow (CeleryExecutor + KEDA + PgBouncer) | Sub-chart Helm |
| **Data** | Iceberg REST Catalog | Deployment propio |
| **Data** | Spark Connect (`personal_ai_spark_connect`) | Deployment propio |
| **Data** | Init Iceberg Namespaces Job | Job propio |
| **Analytics** | Trino | Sub-chart Helm |
| **Analytics** | Metabase | Deployment propio |

---

## Vía 1: Terminal con Skaffold

### Instalación

```bash
# Windows (via chocolatey)
choco install skaffold

# O descarga directa
curl -Lo skaffold.exe https://storage.googleapis.com/skaffold/releases/latest/skaffold-windows-amd64.exe
```

### Comandos del día a día

```bash
# ── Levantar solo la base (API + Worker) ──
skaffold run

# ── Levantar el stack de datos (Airflow + Spark + Iceberg) ──
skaffold run -p data

# ── Levantar el stack analítico (Trino + Metabase) ──
skaffold run -p analytics

# ── Modo desarrollo con hot-reload (solo base) ──
skaffold dev

# ── Bajar el stack de datos limpiamente ──
skaffold delete -p data

# ── Bajar el stack analítico ──
skaffold delete -p analytics

# ── Bajar TODO ──
skaffold delete
```

### Primeros pasos: instalar dependencias de los charts

```bash
# Instalar dependencias del base stack (OTEL Collector)
helm dependency update ./helm/1-base-stack

# Instalar dependencias del data stack (Airflow)
helm dependency update ./helm/2-data-stack

# Instalar dependencias del analytics stack (Trino)
helm dependency update ./helm/3-analytics-stack
```

> [!IMPORTANT]
> El comando `helm dependency update` solo se necesita correr **una vez** (o cuando cambiás versiones en `Chart.yaml`). Descarga los sub-charts a la carpeta `charts/` dentro de cada stack.

### Flujo de trabajo típico (desarrollo del backend)

```bash
# Día 1: Solo necesito la API funcionando
skaffold run
# → Compila personal_ai_api y personal_ai_worker
# → Instala base-stack en k3d
# → API disponible en localhost:80

# Necesito probar un DAG de ETL
skaffold run -p data
# → Compila personal_ai_airflow y personal_ai_spark_connect
# → Levanta Airflow, Iceberg y Spark Connect
# → Airflow UI en localhost:8081/airflow

# Terminé con el ETL, quiero ver dashboards
skaffold delete -p data        # Libera ~4GB de RAM
skaffold run -p analytics
# → Levanta Trino y Metabase
# → Metabase en localhost:8081/metabase
```

---

## Vía 2: Panel Visual con Tilt

### Instalación

```bash
# Windows (via chocolatey)
choco install tilt

# O via Scoop
scoop install tilt
```

### Uso

```bash
# Desde la raíz del proyecto
tilt up
```

Se abre automáticamente **http://localhost:10350** con el panel de control.

### Panel de control

```
┌─────────────────────────────────────────────────────┐
│  BMO Cluster — Tilt Dashboard                       │
├─────────────────────────────────────────────────────┤
│  🟢 base-stack                              [RUNNING]│
│     ├── api-deployment          ► :8000             │
│     └── worker-deployment                           │
│                                                     │
│  ⏸️  data-stack                             [PAUSED] │
│     ├── airflow-webserver    [▶ Trigger]            │
│     ├── airflow-scheduler    [▶ Trigger]            │
│     ├── iceberg-rest         [▶ Trigger]            │
│     └── spark-connect        [▶ Trigger]  ► :4040  │
│                                                     │
│  ⏸️  analytics-stack                        [PAUSED] │
│     ├── trino-coordinator    [▶ Trigger]            │
│     ├── trino-worker         [▶ Trigger]            │
│     └── metabase             [▶ Trigger]  ► :3000  │
└─────────────────────────────────────────────────────┘
```

- **Base**: arranca automáticamente al hacer `tilt up`
- **Data / Analytics**: tienen botón **▶ Trigger** — solo se levantan cuando hacés click

### Ventajas de Tilt sobre Skaffold CLI

| Feature | Skaffold | Tilt |
|---------|----------|------|
| Logs en tiempo real | `kubectl logs` manual | Panel web integrado |
| Rebuild automático | `skaffold dev` | Siempre activo |
| Botones on/off | No | ✅ Por recurso |
| Ver estado del pod | No | ✅ Dashboard |
| Compartir en equipo | Sí | Sí |

---

## Cómo funciona la inteligencia de Skaffold

### Lazy Building (Compilación Perezosa)

Skaffold lee tu chart antes de compilar y determina qué imágenes se necesitan:

```
skaffold run           → Solo compila: personal_ai_api + personal_ai_worker
skaffold run -p data   → Solo compila: personal_ai_airflow + personal_ai_spark_connect
skaffold run -p analytics → No compila ninguna imagen propia (Trino y Metabase son públicas)
```

### Inyección de Tags Automática

En tus charts usás `image: personal_ai_api:latest`. Skaffold reemplaza `latest` por un tag único generado en el momento del build (ej: `personal_ai_api:v1.2-dirty-abc123`). Esto garantiza que k3d siempre corra el código exacto que tenés en tu editor.

### Hot-Reload con `skaffold dev`

Con `skaffold dev` (o `tilt up`):
1. Modificás un archivo `.py` en `src/`
2. Skaffold/Tilt detecta el cambio
3. Reconstruye **solo la capa afectada** del Dockerfile
4. Importa la nueva imagen en k3d
5. Reinicia el pod en Kubernetes

Todo en segundos, sin escribir comandos.

---

## Relación con los YAMLs existentes en `k8s/`

Los archivos en `k8s/prod/` y `k8s/lakehouse/` **siguen siendo la fuente de verdad**. Los templates en `helm/` son una reorganización de esos mismos YAMLs en Umbrella Charts:

| Archivo original | Nuevo destino en Helm |
|-----------------|----------------------|
| `k8s/prod/apps-deployment.yaml` | `helm/1-base-stack/templates/04-apps-deployment.yaml` |
| `k8s/prod/infisical-config.yaml` | `helm/1-base-stack/templates/01-infisical-config.yaml` |
| `k8s/prod/app-configmap.yaml` | `helm/1-base-stack/templates/02-app-configmap.yaml` |
| `k8s/prod/traefik-middlewares.yaml` | `helm/1-base-stack/templates/03-traefik-middlewares.yaml` |
| `k8s/prod/keda-scaler.yaml` + `api-hpa.yaml` | `helm/1-base-stack/templates/05-keda-scalers.yaml` |
| `k8s/prod/otel-rbac.yaml` | `helm/1-base-stack/templates/06-otel-rbac.yaml` |
| `k8s/airflow/helm-values.yaml` | `helm/2-data-stack/values.yaml` (bajo clave `airflow:`) |
| `k8s/lakehouse/01-iceberg-rest.yaml` | `helm/2-data-stack/templates/01-iceberg-rest.yaml` |
| `k8s/lakehouse/02-spark-connect.yaml` | `helm/2-data-stack/templates/02-spark-connect.yaml` |
| `k8s/lakehouse/03-init-iceberg-namespaces.yaml` | `helm/2-data-stack/templates/03-init-iceberg-namespaces.yaml` |
| `k8s/lakehouse/trino-values.yaml` | `helm/3-analytics-stack/values.yaml` (bajo clave `trino:`) |
| `k8s/prod/metabase-deployment.yaml` | `helm/3-analytics-stack/templates/01-metabase.yaml` |

> [!NOTE]
> Los archivos en `k8s/` pueden seguir usándose con `kubectl apply` directamente para operaciones puntuales o debugging. Los Umbrella Charts son la vía de orquestación completa.

---

## Prerequisitos del sistema

```bash
# Verificar que tenés todo instalado
kubectl version --client    # kubectl CLI
helm version                # Helm 3.x
k3d version                 # k3d (tu runtime de Kubernetes local)
skaffold version            # Skaffold (opcional si usás solo Tilt)
tilt version                # Tilt (opcional si usás solo Skaffold)
```

El cluster k3d debe estar corriendo y configurado con el nombre `bmo-cluster` (referenciado en el Tiltfile con `allow_k8s_contexts('k3d-bmo-cluster')`).

---

## Troubleshooting

### Error: "chart not found" al correr skaffold

```bash
# Solución: descargar dependencias primero
helm dependency update ./helm/1-base-stack
helm dependency update ./helm/2-data-stack
helm dependency update ./helm/3-analytics-stack
```

### Error: "image not found" en k3d

Skaffold carga automáticamente las imágenes en k3d con `local.push: false`. Si usás Tilt directamente sin Skaffold, asegurate de que el registry de k3d esté configurado o usá:

```bash
k3d image import personal_ai_api:latest -c bmo-cluster
```

### Airflow no arranca con el data-stack

Verificar que los secrets de Infisical ya estén sincronizados antes de levantar el data-stack:

```bash
kubectl get secret app-secrets -n personal-ai
kubectl get secret airflow-metadata -n personal-ai
kubectl get secret airflow-pgbouncer-config -n personal-ai
```
2. ¿Hay que eliminar lo que está corriendo?
Sí, hay que hacer una migración manual una sola vez. Skaffold no borra lo que desplegaste con kubectl apply directamente — solo maneja lo que él mismo instaló. La situación es:

El problema
Tu estado actual: recursos desplegados con kubectl apply -f k8s/prod/... directamente.
El nuevo estado objetivo: recursos gestionados por Helm vía Skaffold.

Helm y kubectl apply no se llevan bien juntos — si Helm encuentra un recurso que ya existe pero él no creó, puede fallar o dejar el estado inconsistente.

Lo que tenés que hacer (una sola vez)
bash
# 1. Bajar todo lo que está corriendo actualmente (manual)
kubectl delete -f k8s/prod/apps-deployment.yaml
kubectl delete -f k8s/prod/app-configmap.yaml
kubectl delete -f k8s/prod/infisical-config.yaml
kubectl delete -f k8s/prod/traefik-middlewares.yaml
kubectl delete -f k8s/prod/keda-scaler.yaml
kubectl delete -f k8s/prod/api-hpa.yaml
kubectl delete -f k8s/prod/otel-rbac.yaml
kubectl delete -f k8s/prod/metabase-deployment.yaml
# Si tenías Airflow instalado con Helm:
helm uninstall bmo-airflow -n personal-ai
# Si tenías Iceberg/Spark corriendo:
kubectl delete -f k8s/lakehouse/01-iceberg-rest.yaml
kubectl delete -f k8s/lakehouse/02-spark-connect.yaml
kubectl delete -f k8s/lakehouse/03-init-iceberg-namespaces.yaml
kubectl delete -f k8s/lakehouse/spark-connect-keda.yaml
# Si tenías Trino:
helm uninstall trino -n personal-ai
# 2. Verificar que no queda nada
kubectl get all -n personal-ai
# 3. Descargar dependencias de los charts (solo la primera vez)
helm dependency update ./helm/1-base-stack
helm dependency update ./helm/2-data-stack
helm dependency update ./helm/3-analytics-stack
# 4. Levantar todo con Skaffold
skaffold run

# Verificar que los secrets importantes siguen antes de proceder
kubectl get secret app-secrets -n personal-ai
kubectl get secret kafka-ca-cert -n personal-ai
kubectl get secret airflow-metadata -n personal-ai
