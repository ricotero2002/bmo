# ============================================================
# Tiltfile — Panel de Control Visual del Cluster BMO
# ============================================================
# Sintaxis: Starlark (subconjunto de Python)
#
# USO:
#   tilt up          → Abre el panel en http://localhost:10350
#   tilt down        → Baja todo limpiamente
#
# En el panel web verás 3 bloques:
#   🟢 base-stack    → Arranca automáticamente (API + Worker)
#   ⏸️  data-stack    → Botón manual (Airflow + Spark + Iceberg)
#   ⏸️  analytics-stack → Botón manual (Trino + Metabase)
# ============================================================

# ── Configuración global ──
version_settings(constraint='>=0.33.0')

# ── Helpers para k3d ──
# Tilt necesita saber cómo cargar imágenes en el cluster local
# En k3d, usamos el registry interno o carga directa
allow_k8s_contexts('k3d-mycluster')

# ============================================================
# BLOQUE 1: BASE STACK (Siempre encendido, automático)
# ============================================================
# Incluye: Namespace, Infisical, ConfigMap, API FastAPI,
#          Worker Celery, KEDA scalers, Traefik middlewares, OTEL
base_yaml = helm(
    './helm/1-base-stack',
    name='base-stack',
    namespace='personal-ai',
    set=['otel-collector.mode=deployment'],
)
k8s_yaml(base_yaml)

# Recursos del base stack con labels y puertos locales
k8s_resource(
    'api-deployment',
    port_forwards=['8000:8000'],
    labels=['base'],
)
k8s_resource(
    'worker-deployment',
    labels=['base'],
)

# ── Build de imágenes propias (Tilt detecta cambios y reconstruye) ──
docker_build(
    'personal_ai_api',
    context='.',
    dockerfile='docker/Dockerfile',
    target='final-api',
    # Solo observa cambios en src/ y requirements/ para no reconstruir innecesariamente
    only=['src/', 'requirements/', 'docker/'],
)

docker_build(
    'personal_ai_worker',
    context='.',
    dockerfile='docker/Dockerfile',
    target='final-worker',
    only=['src/', 'requirements/', 'docker/'],
)

# ============================================================
# BLOQUE 2: DATA STACK (Manual — botón Play en el panel)
# ============================================================
# Incluye: Airflow (CeleryExecutor + KEDA) + Iceberg REST + Spark Connect
# + Job de inicialización de namespaces del Lakehouse
data_yaml = helm(
    './helm/2-data-stack',
    name='data-stack',
    namespace='personal-ai',
)
k8s_yaml(data_yaml)

# Le decimos a Tilt que NO lo prenda automáticamente
# El usuario hace click en "▶ Trigger" desde el panel web
k8s_resource(
    'airflow-webserver',
    trigger_mode=TRIGGER_MODE_MANUAL,
    labels=['data'],
)
k8s_resource(
    'airflow-scheduler',
    trigger_mode=TRIGGER_MODE_MANUAL,
    labels=['data'],
)
k8s_resource(
    'airflow-worker',
    trigger_mode=TRIGGER_MODE_MANUAL,
    labels=['data'],
)
k8s_resource(
    'iceberg-rest',
    trigger_mode=TRIGGER_MODE_MANUAL,
    labels=['data'],
)
k8s_resource(
    'spark-connect',
    trigger_mode=TRIGGER_MODE_MANUAL,
    labels=['data'],
    port_forwards=['4040:4040'],  # Spark UI accesible en localhost:4040
)

# Build de la imagen de Airflow (solo cuando está activo el data stack)
docker_build(
    'personal_ai_airflow',
    context='.',
    dockerfile='data_tooling/airflow/Dockerfile',
    only=['data_tooling/airflow/', 'src/'],
)

# Build de la imagen de Spark Connect
docker_build(
    'personal_ai_spark_connect',
    context='.',
    dockerfile='docker/spark/Dockerfile.spark-connect',
    only=['docker/spark/'],
)

# ============================================================
# BLOQUE 3: ANALYTICS STACK (Manual — botón Play en el panel)
# ============================================================
# Incluye: Trino (consultas SQL sobre Lakehouse) + Metabase (BI)
analytics_yaml = helm(
    './helm/3-analytics-stack',
    name='analytics-stack',
    namespace='personal-ai',
)
k8s_yaml(analytics_yaml)

k8s_resource(
    'trino-coordinator',
    trigger_mode=TRIGGER_MODE_MANUAL,
    labels=['analytics'],
)
k8s_resource(
    'trino-worker',
    trigger_mode=TRIGGER_MODE_MANUAL,
    labels=['analytics'],
)
k8s_resource(
    'metabase',
    trigger_mode=TRIGGER_MODE_MANUAL,
    labels=['analytics'],
    port_forwards=['3000:3000'],  # Metabase UI en localhost:3000
)
