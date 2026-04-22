# BMO Lakehouse — Notas de Arquitectura y Preguntas Abiertas

---

## 1. Por qué el catálogo REST necesita PostgreSQL (no SQLite)

El servidor `tabulario/iceberg-rest` guarda internamente la lista de tablas, namespaces y sus metadatos en una **base de datos relacional**. Por defecto usa **SQLite** en memoria o en disco local dentro del contenedor.

### El problema con SQLite
SQLite **no soporta concurrencia real**. Cuando dbt intenta crear/reemplazar dos tablas Gold al mismo tiempo (2 threads), ambas operaciones hacen un `DELETE + INSERT` en `iceberg_tables`. SQLite usa locks de archivo completo, y cuando dos procesos compiten, el segundo falla con `UncheckedSQLException: Unknown failure` o `Failed to execute: DELETE FROM iceberg_tables`.

### La solución: PostgreSQL como backend del catálogo
Si el servidor REST usa PostgreSQL como backend, maneja las escrituras concurrentes con bloqueos a nivel de fila (row-level locking), lo que permite múltiples threads sin colisiones.

> ✅ **IMPLEMENTADO** en `docker/docker-compose.yml`: servicio `postgres-catalog` + variables `CATALOG_CATALOG__IMPL`, `CATALOG_URI`, `CATALOG_JDBC_USER/PASSWORD`. Permite volver a `threads: 2` en dbt. **El catálogo arranca vacío tras este cambio — re-ejecutar Bronze → Silver → Gold una vez.**

---

## 2. Spark Checkpointing — Tolerancia a fallos en tiempo de ejecución

Spark tiene dos mecanismos para no perder trabajo si un job falla a mitad:

### 2a. Checkpointing de RDD/DataFrame (Batch)
```python
spark.sparkContext.setCheckpointDir("s3://warehouse/checkpoints/")
df.checkpoint()  # persiste el plan de ejecución hasta ese punto
```
- **Cuándo usarlo**: cuando tenés una cadena de transformaciones muy larga y querés "guardar progreso" para que si Spark se cae, no empiece de cero.
- **En nuestro caso**: el script `ingest_bronze.py` es corto, así que no aplica aún. Cuando haya transformaciones complejas de múltiples stages, sí.

### 2b. Structured Streaming Checkpointing (para Streaming futuro)
Si en el futuro procesás datos en tiempo real (Kafka, etc.):
```python
query = df.writeStream \
    .option("checkpointLocation", "s3://warehouse/checkpoints/bronze_stream/") \
    .toTable("lakehouse.bronze.raw_llm_traces")
```
Spark guarda en S3 exactamente qué offsets ya procesó, permitiendo restart exactamente desde donde se cortó.

> **Nota importante**: Para el pipeline actual (batch), el equivalente al checkpoint es que Iceberg es **ACID**: si la escritura falla a mitad, el snapshot parcial no se "commitea" y la tabla queda en su estado anterior. No se corrompe nunca.

---

## 3. Cómo Airflow preserva el estado de tareas

Airflow guarda todo en su **base de datos interna** (actualmente SQLite dentro del contenedor):

### Qué guarda Airflow
| Concepto | Descripción |
|---|---|
| `DagRun` | Cada ejecución del DAG completo, con su `run_id` y estado |
| `TaskInstance` | Cada tarea individual, su estado (success/failed/running), start/end time |
| `XCom` | Mensajes que las tareas pueden pasarse entre sí |
| Logs | Los logs de cada intento están en disco (`/opt/airflow/logs/`) |

### Cómo se recupera de un fallo
- Si una tarea falla, Airflow la marca `FAILED` pero el `DagRun` queda `FAILED` (no borra nada).
- Podés hacer **Clear** en la UI: solo re-ejecuta las tareas necesarias, no las que ya estaban en verde.
- Con `retries: 3` en el operador, Airflow reintenta automáticamente N veces antes de marcarla `FAILED`.

### Limitación actual
Nuestro Airflow usa `SequentialExecutor` + SQLite, lo que significa que **corre de a una tarea por vez** y no es tolerante a fallos del propio proceso de Airflow. Para producción, se necesita `LocalExecutor` o `CeleryExecutor` + PostgreSQL.

---

## 4. Idempotencia en la ingesta Bronze

**Estado actual**: `Ingesta Bronze completada en lakehouse.bronze.raw_llm_traces. Total rows: 381`

La idempotencia significa: **ejecutar la misma ingesta N veces debe dar el mismo resultado** (sin duplicados).

### El problema actual
El script hace `CTAS` (Create Table As Select) la primera vez, y luego `INSERT INTO` sin deduplicación. Ejecutar dos veces = duplicar filas.

### Cómo garantizar idempotencia real

**Opción A – MERGE (upsert con clave primaria)**:
```python
spark.sql(f"""
    MERGE INTO {full_table_name} target
    USING staging_view source
    ON target.run_id = source.run_id
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
""")
```
Requiere definir `run_id` como clave única.

**Opción B – DELETE + INSERT por fecha de ejecución** (más simple para batch diario):
```python
execution_date = args.execution_date  # pasado por Airflow
spark.sql(f"DELETE FROM {full_table_name} WHERE date(ingested_at) = '{execution_date}'")
df_clean.writeTo(full_table_name).append()
```

**Opción C – Iceberg Overwrite por partición** (la más Iceberg-nativa):
```python
df_clean.writeTo(full_table_name).overwritePartitions()
# Reemplaza solo las particiones afectadas, atómicamente
```

> ✅ **IMPLEMENTADO** en `ingest_bronze.py`: se usa `overwritePartitions()` + tabla particionada por `days(ingested_at)`. Los reintentos de Airflow reemplazan la partición del día sin generar duplicados. Se agregó `expire_snapshots` al final de cada ingesta exitosa.

---

## 5. Ver el Data Lakehouse — Interfaces disponibles

### 5a. DBeaver (recomendado, gratuito)
- Driver: **Apache Hive** o **Spark**
- Host: `localhost`, Port: `10000`, User: cualquiera
- Podés hacer `SELECT * FROM lakehouse.bronze.raw_llm_traces LIMIT 100`



### 5b. Spark UI — Jobs en ejecución
- URL: http://localhost:4040
- Muestra stages, tasks, DAGs de ejecución, uso de memoria

### 5c. MinIO Console — Ver archivos físicos
- URL: http://localhost:9001 (user: `lakehouse` / pass: `lakehouse123`)
- Verás la estructura: `warehouse/bronze/raw_llm_traces/data/*.parquet` + `metadata/*.json`

### 5d. Apache Superset (para dashboards)
Agregar al docker-compose y conectar al Thrift Server:
```yaml
superset:
  image: apache/superset:latest
  ports:
    - "8088:8088"
```
Conexión SQLAlchemy: `hive://localhost:10000/default`

Superset estará disponible en http://localhost:8088 (admin/admin).
Para conectarlo al lakehouse:
Settings → Database Connections → + Database → Apache Hive → hive://host.docker.internal:10000/default.

### 5e. Alternativas SQL potentes
- **Trino**: se conecta directamente al catálogo REST de Iceberg sin pasar por el Thrift Server
- **DuckDB**: puede leer Parquet directamente de MinIO con `read_parquet('s3://warehouse/...')`

---

## 6. Arquitectura: `docker/docker-compose.yml` (Infraestructura Base)

```
MinIO (almacenamiento) ← REST catalog (directorio) ← spark-iceberg (notebooks)
```

### `spark-iceberg` (tabulario/spark-iceberg)
**No es el Spark que usa Airflow**. Es una instancia de Spark con Jupyter para **exploración interactiva**:
- Jupyter Notebooks en puerto 8888
- Spark UI en puerto 8080
- Viene preconfigurado con JARs de Iceberg
- **Piénsalo como**: el "playground del data scientist" — para explorar y experimentar manualmente

### `rest` (tabulario/iceberg-rest)
**Es el catálogo de Iceberg**. No procesa datos, no es un Spark:
- Expone una API HTTP en puerto 8181
- Guarda en su base de datos: "existe la tabla `lakehouse.bronze.raw_llm_traces`, sus metadatos están en `s3://warehouse/.../metadata/`"
- **Piénsalo como**: el "directorio telefónico" del lakehouse. No tiene los datos, sabe dónde están.

Flujo de lectura:
```
Spark → pregunta al REST: ¿dónde está lakehouse.bronze.raw_llm_traces?
      → REST responde: en s3://warehouse/bronze/.../metadata/snap-123.json
      → Spark lee el metadata directamente de MinIO
      → Spark lee los .parquet directamente de MinIO
```

### `minio` y `minio-init`
- **MinIO**: almacenamiento físico (equivalente a S3). Aquí viven `.parquet` y `.json` de metadata Iceberg.
- **minio-init**: job one-shot que crea los buckets al iniciar el entorno.

---

## 7. Arquitectura: `data_tooling/docker-compose.spark-airflow.yml` (Pipeline)

### `spark-thrift`
**No tiene relación de Master/Worker con el `spark-iceberg` del otro compose**. Son instancias completamente independientes:
- Corre en modo `local[*]` (usa todos los CPUs del host, sin cluster distribuido)
- Expone el **Thrift Server** (HiveServer2) en el puerto 10000
- **Propósito**: ser el "motor SQL" al que se conecta dbt via JDBC
- **Piénsalo como**: un servidor de base de datos SQL, pero por debajo usa Spark

### Por qué hay dos Sparks distintos

| | `spark-iceberg` (infra) | `spark-thrift` (pipeline) |
|---|---|---|
| **Propósito** | Notebooks / exploración | Pipeline / dbt |
| **Interfaz** | Jupyter HTTP | HiveServer2 Thrift |
| **Quién lo usa** | Data Scientists | Airflow / dbt |
| **Comparten** | Mismo catálogo REST | Mismo catálogo REST |

Ambos ven las mismas tablas porque apuntan al mismo catálogo REST y al mismo MinIO.

---

## 8. Escalabilidad a 1 TB+ — Qué cambia y qué aguanta

### Lo que YA escala bien (sin cambios)
- **MinIO → S3**: cambiar el endpoint y credenciales, el código no cambia.
- **Iceberg como formato**: diseñado para petabytes. Particionado, pruning y snapshots funcionan igual con 1 GB o 1 PB.
- **dbt models**: las queries SQL son las mismas, Spark se encarga del paralelismo.

### Lo que NO escala en la configuración actual

| Problema | Causa | Solución para producción |
|---|---|---|
| Spark `local[*]` | Un solo proceso, limitado por RAM del host | Spark en Kubernetes, EMR, o Dataproc |
| SQLite en REST catalog | No soporta concurrencia, no persiste tras restart | **PostgreSQL** como backend |
| SQLite en Airflow | Solo 1 tarea paralela, no es HA | PostgreSQL + CeleryExecutor |
| Sin particionado | Scans completos de tabla | `PARTITIONED BY (days(ingested_at))` en la DDL |

### Cómo manejaría 1000 GB sin perder datos
1. **Airflow**: con `retries=3`, si la red falla, reintenta. Con idempotencia, el retry no genera duplicados.
2. **Spark**: `local[*]` puede manejar decenas de GB si hay RAM suficiente. Para 1 TB necesitás distribuir en múltiples nodos.
3. **Iceberg ACID**: si Spark se cae a mitad de escribir, el snapshot no se confirma → la tabla queda intacta. Los archivos parciales se limpian con `CALL system.expire_snapshots(...)`.
4. **MinIO distribuido**: en producción, MinIO con erasure coding o directamente S3.

### Camino de migración sugerido
```
Dev actual       → Staging                  → Producción
local[*] Spark   → Spark Docker Swarm       → Spark en Kubernetes / EMR
SQLite catálogo  → PostgreSQL               → PostgreSQL RDS / Aurora
SQLite Airflow   → PostgreSQL               → Airflow MWAA / Astronomer
MinIO local      → MinIO distribuido        → AWS S3
```

---

## 9. Plan de implementación: PostgreSQL para el catálogo REST

Cambios a realizar en `docker/docker-compose.yml`:

```yaml
services:
  # NUEVO: base de datos para el catálogo Iceberg
  postgres-catalog:
    image: postgres:16-alpine
    container_name: bmo_catalog_db
    environment:
      POSTGRES_DB: iceberg_catalog
      POSTGRES_USER: iceberg
      POSTGRES_PASSWORD: iceberg_secret
    volumes:
      - postgres-catalog-data:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U iceberg -d iceberg_catalog"]
      interval: 5s
      timeout: 5s
      retries: 5

  rest:
    image: tabulario/iceberg-rest:latest
    container_name: bmo_lakehouse_rest
    depends_on:
      postgres-catalog:
        condition: service_healthy
      minio:
        condition: service_started
    environment:
      AWS_ACCESS_KEY_ID: ${MINIO_ROOT_USER:-lakehouse}
      AWS_SECRET_ACCESS_KEY: ${MINIO_ROOT_PASSWORD:-lakehouse123}
      AWS_REGION: us-east-1
      CATALOG_WAREHOUSE: s3://warehouse/
      CATALOG_IO__IMPL: org.apache.iceberg.aws.s3.S3FileIO
      CATALOG_S3_ENDPOINT: http://minio:9000
      CATALOG_S3_PATH_STYLE_ACCESS: "true"
      # NUEVO: usar PostgreSQL en lugar de SQLite
      CATALOG_CATALOG__IMPL: org.apache.iceberg.jdbc.JdbcCatalog
      CATALOG_URI: jdbc:postgresql://postgres-catalog:5432/iceberg_catalog
      CATALOG_JDBC_USER: iceberg
      CATALOG_JDBC_PASSWORD: iceberg_secret
    ports:
      - "8181:8181"
    restart: unless-stopped

volumes:
  minio-data:
  postgres-catalog-data:   # NUEVO
```

### Efectos de este cambio
- ✅ Permite `threads: 2` en dbt sin colisiones
- ✅ El catálogo persiste entre reinicios del contenedor `rest`
- ✅ Soporta múltiples writers concurrentes (Airflow + Notebooks al mismo tiempo)
- ⚠️ El catálogo arrancará vacío (hay que re-ejecutar Bronze → Silver → Gold una vez)
---

## 10. Resolución de Conflictos: dbt-core vs dbt-adapters (Protobuf)

En versiones >= 1.9.0 de dbt, existe un conflicto conocido:
- `dbt-core` exige `protobuf < 6`.
- `dbt-adapters` (nuevos) exigen `protobuf >= 6`.

**Solución aplicada**: Usar `dbt-spark[PyHive]==1.8.0`. Esta versión es compatible con el motor de Airflow y el stack de PostgreSQL sin generar conflictos de librerías base.

---

## 11. Guía de Conexión en Superset (Visualización)

Una vez que `bmo_lakehouse_superset` esté corriendo:

1. **Acceso**: http://localhost:8088 (User: `admin` / Pass: `admin`).
2. **Crear Conexión**: *Settings → Database Connections → + Database*.
3. **Seleccionar**: Apache Hive.
4. **SQLAlchemy URI**: `hive://bmo_lakehouse_spark:10000/demo`
5. **Explorar**: Ahora podés ir a *SQL Lab* y consultar tus tablas:
   ```sql
   SELECT * FROM demo.bronze.raw_llm_traces;
   SELECT * FROM demo.silver.stg_agent_runs;
   SELECT * FROM demo.gold.fact_llm_costs;
   ```

---

## 12. Resolución de Problemas: NoSuchKeyException y S3 Pathing

### El Problema
Durante la implementación, surgió un error recurrente de tipo `NoSuchKeyException` (404) al consultar tablas desde Superset o dbt. 

**Causa raíz**: El servidor de Spark (Thrift Server) y el Catálogo REST estaban usando estilos de direccionamiento S3 incompatibles:
1. **Virtual Host Style**: Intenta usar el nombre del bucket como subdominio (ej: `http://warehouse.minio:9000`).
2. **Path Style**: Usa el nombre del bucket como parte de la ruta (ej: `http://minio:9000/warehouse`).

Esto causaba que los archivos `.metadata.json` (escritos por el Catálogo) se guardaran en buckets físicos distintos a los archivos de datos (escritos por Spark), haciendo que las tablas fueran "invisibles" o dieran error de "archivo no encontrado".

### La Solución
Se aplicaron dos cambios críticos para unificar el comportamiento:
* **En Spark**: Se montó un archivo `spark-defaults.conf` con la propiedad `spark.sql.catalog.demo.s3.path-style.access true`.
* **En MinIO**: Se activó la variable `MINIO_DOMAIN=minio:9000` para que el servidor pueda procesar correctamente peticiones de ambos estilos.

### Estructura de Archivos Actual
Gracias a esta unificación, la jerarquía en MinIO ahora es limpia y predecible:
- **Bucket**: `warehouse/` (Único punto de entrada).
- **Prefixes**: 
  - `warehouse/bronze/` (Datos crudos).
  - `warehouse/silver/` (Datos limpios).
  - `warehouse/gold/` (Tablas finales para BI).

---

## 13. ¿Por qué usamos el catálogo "demo"?

El nombre `demo` es el identificador del catálogo Iceberg configurado por defecto en la imagen de `tabulario/spark-iceberg`. 
* **Función**: Actúa como el contenedor de nivel superior en la jerarquía SQL: `catalog.schema.table`.
* **Razón**: Mantenerlo simplifica enormemente la configuración, ya que todas las herramientas del stack (Jupyter, Spark, REST Catalog) vienen pre-sintonizadas para este nombre.

---

## 14. Estructura de dbt y Gestión de Git

Al inicializar dbt, aparecen múltiples archivos en la carpeta `data_tooling/dbt/`. Aquí te explico qué es cada uno:

### Archivos de Configuración
* **`dbt_project.yml`**: El "corazón" de dbt. Define el nombre del proyecto, qué carpetas contienen modelos, y configuraciones globales de materialización.
* **`profiles.yml`**: Define las credenciales de conexión (Thrift Server, puerto, catálogo).
* **`packages.yml`** / **`package-lock.yml`**: Gestionan las dependencias externas (como `dbt_utils`). Similar a un `requirements.txt`.
* **`macros/`**: Funciones SQL reutilizables.

### Lo que DEBES incluir en Git
- Todos los archivos `.sql` y `.yml` dentro de `models/`.
- `dbt_project.yml`, `profiles.yml`, `packages.yml`.
- `macros/`.

### Lo que NO debe ir a Git (GitIgnore)
Debes agregar (o mantener) lo siguiente en tu `.gitignore` para evitar subir basura o código compilado:
```gitignore
# dbt artifacts
data_tooling/dbt/target/
data_tooling/dbt/dbt_packages/
data_tooling/dbt/logs/
data_tooling/dbt/.user.yml
```

> [!TIP]
> Si alguna vez una tabla parece "rota" pero los archivos están en MinIO, lo más probable es que el catálogo de PostgreSQL se haya desincronizado. Borrar la fila correspondiente en la tabla `iceberg_tables` de la base de datos `iceberg_catalog` y re-ejecutar el pipeline suele ser la solución más rápida.
