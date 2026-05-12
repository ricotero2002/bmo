# Pipeline LLM Telemetry — Reporte de Estabilización Fase 9

> **Fecha:** 2026-05-11  
> **Estado:** Estabilizado ✅  
> **Entorno:** K3d (WSL2) → OCI Object Storage → Apache Iceberg 1.5.2 → Airflow 2.10.5 (CeleryExecutor)

---

## 1. Arquitectura del Pipeline (Evolución)

Originalmente, el pipeline operaba con Spark local en cada worker. Tras la Fase 9, hemos migrado a una arquitectura desacoplada mediante **Spark Connect**.

### 1.1 Diagrama de Flujo Actualizado
```
LangSmith API
     │
     ▼
[extract_from_langsmith]  (PythonOperator)
     │  boto3 → s3://bronze/langsmith_raw/date=YYYY-MM-DD/
     ▼
[register_bronze_iceberg] (BashOperator → Spark Connect Client)
     │  Escribe en lakehouse.bronze.langsmith_raw via gRPC
     ▼
[dbt_run_silver]          (BashOperator → dbt via Thrift)
     │  Bronze Iceberg → Silver Iceberg (stg_agent_runs)
     ▼
[spark_evaluate_gold]     (BashOperator → Spark Connect Client)
     │  1. Spark filtra Silver → .toPandas() al Worker
     │  2. Worker evalúa con DeepEval/NIM (Local Python)
     │  3. Spark escribe Gold via gRPC
     ▼
[dbt_run_gold]            (BashOperator → dbt via Thrift)
     │  Agregación final de métricas y costos
     ▼
[end]
```

**Buckets OCI:**
| Bucket | Uso |
|--------|-----|
| `bronze` | Landing zone Parquet raw de LangSmith |
| `warehouse` | Archivos Iceberg (metadata + data files) de todas las capas |

---

## 2. Problemas Encontrados y Soluciones Implementadas

problemas:

webserver:
para que se viera en la url tuve que poner 
   base_url: "http://localhost:8081/airflow"
  y un trafik middleware

tuve que aumentar los tiempos de los probes
y los resources:
  resources:
    limits:
      cpu: "1000m"
      memory: "1Gi"
    requests:
      cpu: "500m"
      memory: "512Mi"

conexion postgresql:
  como saturava mucho la conexiones tuve que hacer un PgBouncer que se conecte con aiven y que todo lo de airflow vaya a ese pgbouncer.

woerker:

Como agarraban las variavlesd e celery externas (las que uso en la api) tuve que no agarrarlas directas de app-secrets sino cambiarlas:
extraEnv: |
  - name: CELERY_BROKER_URL
    valueFrom:
      secretKeyRef:
        name: app-secrets
        key: AIRFLOW__CELERY__BROKER_URL
  - name: CELERY_RESULT_BACKEND
    valueFrom:
      secretKeyRef:
        name: app-secrets
        key: AIRFLOW__CELERY__RESULT_BACKEND

y como tenia problemas con el host name tuve que obtener la ip:
 Inyectamos la IP real del pod
  - name: MY_POD_IP
    valueFrom:
      fieldRef:
        fieldPath: status.podIP

y poner el hostname con args:
  args:
    - "bash"
    - "-c"
    # Usar la IP evita el crasheo de NoneType y elimina el problema de DNS
    - "exec airflow celery worker -q default --celery-hostname $MY_POD_IP"
  
Como uso spark interno tuve que aumentar los limites del worker y usar keada para no saturar el clsuter si no uso airflow 
  replicas: 1
  keda:
    enabled: true
    pollingInterval: 5      # Cada cuántos segundos KEDA revisa la cola
    cooldownPeriod: 30      # Segundos que espera sin tareas antes de matar al worker
    minReplicaCount: 0      # MAGIA: Si no hay DAGs corriendo, 0 workers activos
    maxReplicaCount: 1      # Límite máximo para no saturar tu cluster K3d
  resources:
    requests:
      cpu: "1"
      memory: "3Gi"
    limits:
      cpu: "2"
      memory: "5Gi"

### 2.1 ❌ 403 Forbidden en Hadoop S3A al leer bucket bronze

**Síntoma:**
```
AmazonS3Exception: Forbidden (Status Code: 403)
at S3AFileSystem.s3GetFileStatus → getObjectMetadata
```

**Causa raíz:**  
El SDK de AWS v1 que usa `hadoop-aws 3.3.4` no envía el header `x-amz-content-sha256` en todos los requests. OCI requiere Payload Signing obligatorio. Boto3 lo hace correctamente con `signature_version='s3v4'` + `payload_signing_enabled=True`.

**Configuraciones intentadas sin éxito:**
- `spark.hadoop.fs.s3a.signing-algorithm=AWS4SignerType`
- `AWS_DEFAULT_REGION` como env var  
- Override por bucket (`fs.s3a.bucket.bronze.*`)
- `fs.s3a.multiobjectdelete.enable=false`

**Solución implementada (definitiva):**  
Descarga previa via **boto3** al directorio `/tmp` local del pod. La escritura a Iceberg usa `S3FileIO` (SDK v2) que sí soporta OCI.

**Archivo modificado:** `data_tooling/airflow/tasks/register_bronze.py`
```python
def download_parquets_from_oci(ds, local_dir):
    s3 = boto3.client("s3", ...,
        config=Config(signature_version="s3v4",
                      s3={"payload_signing_enabled": True, "addressing_style": "path"}))
    # Descarga chunks a /tmp/bronze_landing_{ds}/

def register_bronze(ds):
    n_files = download_parquets_from_oci(ds, local_tmp)
    df_new = spark.read.parquet(local_tmp)      # Lee desde /tmp
    df_final.writeTo(full_table_name).overwritePartitions()  # S3FileIO → OK
```

---

### 2.2 ❌ SdkClientException al escribir en Iceberg (SDK v2 sin región)

**Síntoma:**
```
SdkClientException: Unable to load region from any of the providers
Region must be specified via AWS_REGION or aws.region
```

**Causa raíz:**  
El `S3FileIO` de Iceberg usa AWS SDK v2 que busca `AWS_REGION`. Nuestro secret exporta `OCI_REGION`.

**Solución implementada** en `src/providers/lakehouse/spark_utils.py`:
```python
os.environ.setdefault("AWS_REGION", region)
os.environ.setdefault("AWS_DEFAULT_REGION", region)
# + agregar al catálogo:
.config("spark.sql.catalog.lakehouse.client.region", region)
```

---

### 2.3 ❌ OOM / Exit Code 137 (SIGKILL por Kubernetes)

**Causas:**
1. `fast.upload.buffer=bytebuffer` → usa RAM Off-Heap fuera del límite JVM
2. `local[*]` → abre tantos hilos como CPUs del host WSL2 (hasta 16+)
3. Liveness Probe con `failureThreshold=5` y `timeout=20s` muy agresivo

**Soluciones:**

| Parámetro | Antes | Después |
|---|---|---|
| `fs.s3a.fast.upload.buffer` | `bytebuffer` | **`disk`** |
| Spark master | `local[*]` | **`local[2]`** |
| Worker memory limit | `4Gi` | **`5Gi`** |
| `livenessProbe.failureThreshold` | 5 | **20** |
| `livenessProbe.timeoutSeconds` | 20 | **60** |
| `livenessProbe.initialDelaySeconds` | 10 | **120** |

---

### 2.4 ❌ Conflicto de Field Manager en Helm

**Síntoma:**
```
conflict with "kubectl-patch" using apps/v1: 
.spec.template.spec.containers[name="worker"].resources.limits.memory
```

**Causa:** `kubectl patch` manual tomó ownership del campo.  
**Solución:** `helm upgrade --force`

---

### 2.5 ❌ YAML inválido en helm-values.yaml

**Síntoma:** `yaml: line 189: did not find expected key`  
**Causa:** Se eliminó accidentalmente la clave `keda:` al editar, dejando los valores con indentación huérfana.  
**Solución:** Restaurar la clave `keda:` con 2 espacios de indentación bajo `workers:`.

---

### 2.6 ✅ KEDA habilitado

```yaml
workers:
  keda:
    enabled: true
    pollingInterval: 5
    cooldownPeriod: 30
    minReplicaCount: 0
    maxReplicaCount: 1
```
Worker se apaga con 0 tareas, ahorrando ~5Gi de RAM en idle.

---

## 3. Análisis de Compatibilidad

### 3.1 `spark_evaluator.py` — Estado: ⚠️ REQUIERE FIXES

#### Problema A — Checkpoint en S3A (línea 98)
```python
spark.sparkContext.setCheckpointDir("s3a://warehouse/checkpoints/")
# ❌ FALLARÁ: S3A con SDK v1 → 403 en OCI
```
**Fix:** Cambiar a checkpoint local:
```python
spark.sparkContext.setCheckpointDir("/tmp/spark-checkpoints/")
```

#### Problema B — NvidiaJudge requiere credenciales externas
La UDF instancia `NvidiaJudge()` que llama a `LLMFactory.create_judge()`. Requiere `NVIDIA_API_KEY` y hace HTTP requests síncronos por cada fila. Funciona en `local[2]` porque corre en el mismo proceso, pero:
- Falla si la env var no está presente en el pod
- Muy lento a escala (1 API call HTTP por run evaluado)

**Fix corto plazo:** Verificar que `NVIDIA_API_KEY` esté en el secret `app-secrets`.

#### Problema C — `src.evals.eval_utils` con dependencias pesadas
Importa `VectorStoreFactory`, `RecordManagerFactory`, `StatusProvider`. Si estas dependencias fallan al inicializar (credenciales faltantes), el script entero crashea antes de procesar datos.

**Fix:** Aislar la importación de `NvidiaJudge` en un try/except o crear una versión ligera solo para el evaluador Spark.

#### Lo que SÍ es compatible ✅:
- Lectura de `lakehouse.silver.stg_agent_runs` → usa S3FileIO (SDK v2) → OK
- Escritura a `lakehouse.gold.agent_evaluations` → usa S3FileIO → OK
- Creación de tablas con `spark.sql()` → catálogo REST → OK

---

### 3.2 DBT — Estado: ❌ NO FUNCIONA en K3d

#### Problema 1 — `profiles.yml` apunta a Docker Desktop
```yaml
# ACTUAL (incorrecto para K8s)
spark.sql.catalog.lakehouse.uri: http://host.docker.internal:8181
spark.sql.catalog.lakehouse.s3.endpoint: http://host.docker.internal:9000
spark.sql.catalog.lakehouse.s3.access-key-id: lakehouse
spark.sql.catalog.lakehouse.s3.secret-access-key: lakehouse123
```

**Fix requerido:**
```yaml
spark.sql.catalog.lakehouse.uri: http://iceberg-rest-svc.personal-ai.svc.cluster.local:8181
spark.sql.catalog.lakehouse.s3.endpoint: https://${OCI_NAMESPACE}.compat.objectstorage.${OCI_REGION}.oraclecloud.com
spark.sql.catalog.lakehouse.s3.access-key-id: ${OCI_ACCESS_KEY}
spark.sql.catalog.lakehouse.s3.secret-access-key: ${OCI_SECRET_KEY}
```

#### Problema 2 — `/opt/airflow/dbt` no existe en la imagen
El DAG hace `cwd="/opt/airflow/dbt"` pero el Dockerfile no copia ese directorio.

**Fix:** Agregar al `Dockerfile`:
```dockerfile
COPY data_tooling/dbt/ /opt/airflow/dbt/
```

#### Problema 3 — Thrift Server con `NoSuchNamespaceException: default`
El Thrift Server al conectar al catálogo REST busca el namespace `default`. Si no existe, rechaza toda conexión JDBC.

**Fix actual aplicado:** Crear namespace manualmente via curl.  
**Fix permanente pendiente:** Job de Kubernetes que lo cree al arranque.

#### Modelos SQL — Compatibilidad ✅
- `stg_agent_runs.sql`: usa `get_json_object` (SparkSQL nativo) → OK
- `stg_agent_run_anomalies.sql`: depende de `stg_agent_runs` → OK si el anterior funciona
- Modelos Gold: dependen de tablas Silver y Gold Spark → OK estructuralmente

---

## 4. Estabilización Final (Fase 9) — Arquitectura Spark Connect

Tras los problemas de recursos y compatibilidad detectados, se realizó una reingeniería del pipeline para desacoplar el cómputo de Spark del worker de Airflow.

### 4.1 Migración a Spark Connect (Servidor Centralizado)
Se eliminó la necesidad de tener Java y JARs pesados en cada worker de Airflow.
- **Servidor (`02-spark-connect.yaml`)**: Centraliza la resolución de paquetes Maven (`iceberg-spark-runtime`, `hadoop-aws`, etc.).
- **Worker Client**: Ahora es un "thin client" que solo usa `pyspark[connect]`.
- **Beneficio**: Reducción drástica del tamaño de la imagen de Airflow y del consumo de RAM por pod.

### 4.2 Refactor de Evaluación (`spark_evaluator.py`)
Se resolvió la imposibilidad de correr `deepeval` y `NvidiaJudge` en ejecutores Spark remotos.
- **Patrón "Collect -> Evaluate -> Write"**:
    1. Spark filtra la muestra en el servidor remetodo.
    2. Los datos se descargan al worker mediante `.toPandas()`.
    3. La evaluación ocurre en Python nativo en el worker (donde están todas las dependencias de IA y conectividad a NVIDIA NIM).
    4. Los resultados se suben a Iceberg como un DataFrame de Spark.

### 4.3 Optimización de Infraestructura Airflow (K8s)
- **PgBouncer**: Implementado para mitigar la saturación de conexiones hacia la base de datos de metadatos (Aiven).
- **KEDA (Scaling)**: Configurado con `minReplicaCount: 0`. Los workers solo existen cuando hay tareas pendientes.
- **Limpieza de Dependencias**: Se implementó **lazy loading** en los providers del proyecto para evitar que la falta de librerías pesadas bloquee la ejecución de DAGs ligeros.

---

## 5. Estado Final de Tareas del DAG

| Tarea | Estado | Solución Aplicada |
| :--- | :--- | :--- |
| `extract_from_langsmith` | ✅ **OK** | boto3 nativo con payload signing. |
| `register_bronze_iceberg` | ✅ **OK** | Migrado a Spark Connect Client. |
| `dbt_run_silver` | ✅ **OK** | Profiles.yml actualizado para K8s y OCI. |
| `spark_evaluate_gold` | ✅ **OK** | Refactorizado para evaluación local en worker (Pandas). |
| `dbt_run_gold` | ✅ **OK** | Ejecución final de agregaciones. |

---

## 6. Resumen de Errores Críticos Resueltos en Fase 9

| Error | Causa | Solución |
| :--- | :--- | :--- |
| `DATA_SOURCE_NOT_FOUND: iceberg` | Falta de JARs en el servidor | Inyección correcta vía `--packages` en el server. |
| `PySparkNotImplementedError` | Incompatibilidad con Connect | Refactor de `spark_utils.py` para eliminar `sparkContext`. |
| `ModuleNotFoundError: langchain_classic` | Dependencias en worker | Imports dinámicos y limpieza de `requirements.txt`. |
| `StatusCode.UNAVAILABLE` | Espacios en YAML de paquetes | Fix de sintaxis en el comando de arranque del servidor. |

---

## 7. Mejoras Futuras (Post-Estabilización)
1. **Cachear JARs**: Pre-instalar los JARs de Iceberg en la imagen de Spark Connect para acelerar el arranque.
2. **Paralelización**: Implementar threads en el loop de evaluación para llamadas concurrentes a NVIDIA NIM.
3. **Monitoreo**: Integración total de la capa Gold en Metabase.
