# Pipeline LLM Telemetry — Reporte de Estabilización Fase 9

> **Fecha:** 2026-05-10  
> **Entorno:** K3d (WSL2) → OCI Object Storage → Apache Iceberg 1.5.2 → Airflow 2.10.5

---

## 1. Arquitectura del Pipeline

```
LangSmith API
     │
     ▼
[extract_from_langsmith]  (PythonOperator)
     │  boto3 → s3://bronze/langsmith_raw/date=YYYY-MM-DD/chunk_N.parquet
     ▼
[register_bronze_iceberg]  (BashOperator → spark-submit)
     │  boto3 descarga /tmp → Spark lee local → S3FileIO escribe Iceberg Bronze
     ▼
[dbt_run_silver]  (BashOperator → dbt via Thrift)
     │  Bronze Iceberg → Silver Iceberg (stg_agent_runs, stg_agent_run_anomalies)
     ▼
[spark_evaluate_gold]  (BashOperator → spark-submit)
     │  Silver Iceberg → NvidiaJudge UDF → Gold Iceberg (agent_evaluations, agent_errors)
     ▼
[dbt_run_gold]  (BashOperator → dbt via Thrift)
     │  Gold Iceberg → fact_agent_performance, fact_evaluations, fact_llm_costs
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

## 4. Estado Actual por Tarea del DAG

| Tarea | Estado | Bloqueante |
|---|---|---|
| `extract_from_langsmith` | ✅ **FUNCIONA** | — |
| `register_bronze_iceberg` | ✅ **FUNCIONA** | — |
| `dbt_run_silver` | ❌ **ROTO** | profiles.yml + dbt dir faltante + Thrift |
| `spark_evaluate_gold` | ⚠️ **PARCIAL** | Checkpoint S3A + NvidiaJudge deps |
| `dbt_run_gold` | ❌ **ROTO** | Mismo que silver |

---

## 5. Fixes Pendientes — Roadmap

### 🔴 Alta Prioridad (bloquean el E2E)

1. **Checkpoint local en `spark_evaluator.py`** (5 min)
   ```python
   spark.sparkContext.setCheckpointDir("/tmp/spark-checkpoints/")
   ```

2. **Copiar dbt en Dockerfile** (5 min)
   ```dockerfile
   COPY data_tooling/dbt/ /opt/airflow/dbt/
   ```

3. **Actualizar `profiles.yml`** para K8s con OCI (15 min)

4. **Job K8s para inicializar namespaces del catálogo REST** (30 min)

### 🟡 Media Prioridad

5. **Validar `NVIDIA_API_KEY`** en el secret `app-secrets` de Infisical

6. **`--driver-memory 1g`** en `SPARK_BASE` del DAG:
   ```python
   SPARK_BASE = f"spark-submit --master 'local[2]' --driver-memory 1g --packages ..."
   ```

7. **Eliminar `spark.sql.defaultCatalog=lakehouse`** del Thrift Server para evitar el conflicto con el namespace `default`

### 🟢 Mejoras Futuras

8. **Cachear JARs de Spark en la imagen Docker** para evitar descargas de Maven en cada ejecución (~60s y falla sin internet)

9. **Migrar lectura Bronze a Iceberg nativo** cuando `hadoop-aws` tenga soporte completo de OCI Payload Signing (v3.4+)

10. **Reemplazar Thrift por dbt-iceberg** con REST catalog directo, eliminando el Thrift Server como intermediario

11. **Paralelizar evaluaciones** en `spark_evaluator.py` usando async o pool de requests a Nvidia NIM en lugar de 1 por fila

12. **Agregar timeout al `BashOperator`** del DAG para tasks Spark pesadas:
    ```python
    register_bronze_task = BashOperator(
        execution_timeout=timedelta(minutes=30),
        ...
    )
    ```

---

## 6. Configuración Final Estabilizada

### `spark_utils.py` — Configuraciones clave OCI
```python
# Fix SDK v2
os.environ.setdefault("AWS_REGION", region)
os.environ.setdefault("AWS_DEFAULT_REGION", region)

# Iceberg catalog
.config("spark.sql.catalog.lakehouse.s3.payload-signing-enabled", "true")
.config("spark.sql.catalog.lakehouse.s3.checksum-enabled", "false")
.config("spark.sql.catalog.lakehouse.client.region", region)

# Hadoop S3A (warehouse solamente)
.config("spark.hadoop.fs.s3a.signing-algorithm", "AWS4SignerType")
.config("spark.hadoop.fs.s3a.fast.upload.buffer", "disk")  # ← Key fix OOM
```

### `helm-values.yaml` — Worker
```yaml
workers:
  keda:
    enabled: true
    minReplicaCount: 0
    maxReplicaCount: 1
  resources:
    requests: { cpu: "1", memory: "4Gi" }
    limits:   { cpu: "2", memory: "5Gi" }
  livenessProbe:
    initialDelaySeconds: 120
    timeoutSeconds: 60
    periodSeconds: 60
    failureThreshold: 20
```

### Diagrama de Conectividad Validada
```
Worker Pod
    ├─ boto3 (s3v4 + payload_signing)  →  OCI bronze  ✅
    ├─ Spark S3FileIO (SDK v2 + AWS_REGION)  →  OCI warehouse  ✅
    └─ Spark S3A (SDK v1 hadoop-aws)  →  OCI ANY  ❌ 403 (workaround: no usar)

Thrift Pod
    ├─ JDBC/Beeline  →  localhost:10000  ❌ (namespace default issue)
    └─ Iceberg REST  →  iceberg-rest-svc:8181  ✅
```




