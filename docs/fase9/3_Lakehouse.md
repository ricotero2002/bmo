# Fase 9.3 - Lakehouse bootstrap

## Objetivo

Levantar un Lakehouse separado del cluster de Kubernetes, usando Docker Compose dedicado solo para datos analiticos.

## Conceptos necesarios

### Apache Parquet

Apache Parquet es un formato de almacenamiento columnar de código abierto, altamente eficiente y de tipo binario, diseñado para el procesamiento y análisis de grandes volúmenes de datos (Big Data). A diferencia de los formatos basados en filas (como CSV), Parquet almacena los datos de cada columna juntos, lo que permite una compresión superior, menor uso de espacio y consultas mucho más rápidas al leer solo las columnas necesarias. Es ampliamente utilizado en ecosistemas como Apache Spark, Hadoop y Hive para optimizar cargas de trabajo analíticas. 

Características y Beneficios Clave
Almacenamiento Columnar: Al agrupar los datos por columnas, es ideal para consultas que seleccionan pocas columnas de tablas con muchas columnas, según aprenderbigdata.com.

Alta Compresión: Almacena valores similares juntos, lo que mejora la eficiencia de los algoritmos de compresión.
Autodescriptivo: Los metadatos (esquema, estructura) se incluyen en el archivo, facilitando la lectura por diferentes herramientas, señala datos.gob.es.

Soporte de Estructuras Complejas: Maneja datos anidados eficientemente, basado en el paper de Dremel de Google, explica Jerónimo López.

Eficiencia en Lectura: Diseñado para lectura rápida y analítica, aunque menos eficiente en escrituras frecuentes comparado con formatos orientados a filas.

### Apache Iceberg

Aquí es donde los Data Lakes tradicionales fallaban y por qué nació el concepto de "Lakehouse".

Si usas solo MinIO y guardas tus datos en formato Apache Parquet (un formato columnar muy eficiente), sigues teniendo un problema: son solo archivos sueltos. Si quieres hacer un UPDATE de un registro o borrar un dato, tendrías que descargar archivos de 1GB, modificarlos en memoria y volver a subirlos.

Iceberg no es un motor de base de datos ni un servidor que debas instalar. Es una "especificación", una capa matemática de metadatos (archivos ocultos que acompañan a tus datos).

¿Cómo funciona Iceberg en la práctica?

El Árbol de Metadatos: Cuando le dices a Spark que guarde una tabla en formato Iceberg, Iceberg crea un archivo Parquet con los datos reales en MinIO. Pero además, crea un archivo de metadatos (en formato JSON o Avro) que dice: "La tabla 'logs_agente' versión 1 está compuesta por el archivo_A.parquet".

Mutabilidad (ACID): Si haces un UPDATE, Iceberg no sobrescribe archivo_A.parquet. Crea archivo_B.parquet con los datos nuevos y escribe un nuevo archivo de metadatos que dice: "La tabla 'logs_agente' versión 2 ahora ignora la fila 5 del archivo_A y lee el archivo_B". Esto permite múltiples escrituras simultáneas sin corromper la base de datos.

Time Travel: Como Iceberg guarda el historial de qué archivos componían la tabla en cada momento, puedes hacer consultas del tipo: "Haz un SELECT de esta tabla exactamente como estaba ayer a las 3 PM".

Optimización de Búsqueda: Iceberg guarda estadísticas (mínimos y máximos) de cada archivo. Si haces SELECT * WHERE fecha = 'hoy', Iceberg sabe exactamente qué archivos Parquet en MinIO ignorar sin tener que abrirlos, reduciendo tiempos de escaneo de horas a milisegundos.

### Apache Spark

Spark es el "trabajador" de esta arquitectura. No almacena datos de forma persistente; su único trabajo es conectarse al almacenamiento, subir los datos a la memoria RAM, procesarlos en paralelo y escupirlos de nuevo.

¿Por qué Spark y no un script normal de Python?
Python estándar procesa datos en un solo hilo. Si tienes un log de 50 GB, tu script hará un cuello de botella y tu PC colapsará por falta de RAM. Spark utiliza procesamiento distribuido.

Arquitectura Master/Worker: Spark tiene un nodo "Driver" (el director de orquesta) y nodos "Executors" (los obreros). Si le pasas 50 GB de datos, Spark divide esos datos en "particiones" pequeñas y le da un pedazo a cada obrero para que lo procese en la RAM de forma aislada.

DataFrames (Lazy Evaluation): El código que escribes en PySpark es muy similar a Pandas, pero es "perezoso". Cuando le dices df.filter(), Spark no hace nada. Solo construye un plan de ejecución (un grafo) en su cabeza. Solo cuando le dices df.write o df.show(), Spark analiza el plan, lo optimiza al extremo y lanza a todos sus obreros a la vez.

### Uso Conjunto

Imagina que quieres procesar los historiales de LangGraph:

Ingesta a MinIO (Bronze): Tienes tus logs JSON crudos en un bucket de MinIO s3a://bronze/logs/. (En realidad estan en postgresql, tendria que traermelos de ahi primero)

Spark arranca: Inicializas tu sesión de PySpark. Le pasas las credenciales de MinIO y le inyectas las librerías .jar de Iceberg. (Esto supongo que lo haria airflow)

Spark lee (Extract): Le dices a Spark que lea el JSON de MinIO. Spark divide el JSON y lo carga en la RAM como un DataFrame.

Spark transforma (Transform): Aplicas lógica de PySpark para limpiar campos nulos, extraer el thread_id y calcular los tokens usados. Todo esto ocurre en paralelo en la RAM.

Spark + Iceberg escriben (Load): Le indicas a Spark: df.write.format("iceberg").save("s3a://silver/logs_limpios").

La magia final: Spark convierte los datos a Parquet y los envía a MinIO. Inmediatamente después, el conector de Iceberg intercepta la acción y genera los metadatos de la nueva transacción, bloqueando la tabla por milisegundos para asegurar que nadie más escriba al mismo tiempo, y guarda esos metadatos en MinIO.

## Implementacion aplicada



Se actualizo [docker/docker-compose.yml](docker/docker-compose.yml) para que contenga solo servicios de Lakehouse:

1. `spark-iceberg`
    - Imagen `tabulario/spark-iceberg:latest`.
    - Incluye Spark + Iceberg + entorno de notebooks.
    - Puertos:
        - `8888` (Jupyter Notebook)
        - `8080` (Spark UI)
    - Volumenes locales:
        - `lakehouse/warehouse`
        - `lakehouse/notebooks`

2. `minio`
    - Object storage S3-compatible.
    - Expone `9000` (API) y `9001` (Console).

3. `minio-init`
    - Inicializa buckets base del Lakehouse:
        - `bronze`
        - `silver`
        - `gold`
        - `warehouse`

4. `rest`
    - Catalogo REST de Iceberg (`tabulario/iceberg-rest:latest`).
    - Expone `8181`.
    - Usa MinIO como backend S3 del catalogo.

## Stack final (fuera de Kubernetes)

- MinIO para almacenamiento de objetos.
- Spark (imagen Tabular) para procesamiento y notebooks.
- Iceberg REST catalog para metadata centralizada.
- Iceberg como formato transaccional de tablas sobre objetos en S3.

No quedan servicios operacionales (API, DB, Redis, Kafka, Chroma, etc.) en este compose.

## Como levantar

Desde la raiz del repo:

```bash
docker compose -f docker/docker-compose.yml up -d
```

## Verificaciones rapidas

1. Ver contenedores:

    ```bash
    docker compose -f docker/docker-compose.yml ps
    ```

2. Revisar inicializacion de buckets:

    ```bash
    docker logs bmo_lakehouse_minio_init
    ```

3. Validar bootstrap Iceberg en Spark:

    ```bash
    docker logs bmo_lakehouse_spark
    ```

4. Entrar a Spark SQL para inspeccion manual:

    ```bash
docker exec -it bmo_lakehouse_spark spark-sql --driver-memory 512M --conf spark.sql.defaultCatalog=lakehouse --conf spark.sql.catalog.lakehouse=org.apache.iceberg.spark.SparkCatalog --conf spark.sql.catalog.lakehouse.type=rest --conf spark.sql.catalog.lakehouse.uri=http://rest:8181 --conf spark.sql.catalog.lakehouse.warehouse=s3://warehouse/ --conf spark.sql.catalog.lakehouse.io-impl=org.apache.iceberg.aws.s3.S3FileIO --conf spark.sql.catalog.lakehouse.s3.endpoint=http://minio:9000 --conf spark.sql.catalog.lakehouse.s3.path-style-access=true --conf spark.sql.catalog.lakehouse.s3.access-key-id=lakehouse --conf spark.sql.catalog.lakehouse.s3.secret-access-key=lakehouse123 --conf spark.hadoop.fs.s3a.endpoint=http://minio:9000 --conf spark.hadoop.fs.s3a.access.key=lakehouse --conf spark.hadoop.fs.s3a.secret.key=lakehouse123 --conf spark.hadoop.fs.s3a.path.style.access=true --conf spark.hadoop.fs.s3a.connection.ssl.enabled=false
    ```

Luego ejecutar:

```sql
SHOW NAMESPACES IN lakehouse;
SHOW TABLES IN lakehouse.bronze;
SELECT * FROM lakehouse.bronze.agent_events LIMIT 10;
```

## Criterio de done para este frente

1. Compose levanta solo Lakehouse.
2. Buckets `bronze/silver/gold/warehouse` creados.
3. Catalogo Iceberg operativo en Spark.
4. Tabla base `lakehouse.bronze.agent_events` creada y consultable.

## Smoke test automatico

Se agrego el script [scripts/lakehouse_smoke.ps1](scripts/lakehouse_smoke.ps1) para validar de punta a punta:

1. Levanta el compose del Lakehouse.
2. Verifica que `minio-init` termine en `exited|0`.
3. Verifica confirmacion de buckets en logs (`bronze/silver/gold/warehouse`).
4. Verifica namespaces Iceberg (`bronze/silver/gold`).
5. Verifica tabla `lakehouse.bronze.agent_events`.
6. Inserta datos de prueba, valida conteo y metadatos (`snapshots` y `files`).
7. Aplica bootstrap Iceberg (namespaces + tabla) durante el smoke.

### Endurecimiento aplicado en el smoke (estado final)

Para que Spark escriba datos fisicos en MinIO (y no intente AWS real), el smoke usa explicitamente propiedades nativas de Iceberg `S3FileIO`:

1. `spark.sql.catalog.lakehouse.s3.endpoint=http://minio:9000`
2. `spark.sql.catalog.lakehouse.s3.path-style-access=true`
3. `spark.sql.catalog.lakehouse.s3.access-key-id=<user>`
4. `spark.sql.catalog.lakehouse.s3.secret-access-key=<password>`

Ademas, mantiene propiedades `spark.hadoop.fs.s3a.*` como compatibilidad interna de Spark/Hadoop.

Tambien se robustecio la validacion del smoke para soportar salidas de `spark-sql` sin headers (por ejemplo, cuando `count(*)` devuelve solo un numero en pantalla).

### Fix definitivo para `UnknownHostException: rest`

La imagen `tabulario/spark-iceberg` trae una configuracion demo por defecto que apunta a un catalogo REST (`rest:8181`).

En esta implementacion se levanta explicitamente el servicio `rest`, por lo que Spark puede resolver ese host dentro de la red de Docker.

Ademas, para evitar que use otros catalogs por defecto, se usan estos flags en todos los comandos `spark-sql` del smoke:

1. `--conf spark.sql.defaultCatalog=lakehouse`
2. `--conf spark.sql.catalog.lakehouse.type=rest`
3. `--conf spark.sql.catalog.lakehouse.uri=http://rest:8181`

Con esto se controla explicitamente el catalogo objetivo.

## Paso a paso de uso

1. Levantar entorno:

```bash
docker compose -f docker/docker-compose.yml up -d
```

2. Entrar a MinIO Console en `http://localhost:9001`.
3. Entrar a Jupyter en `http://localhost:8888`.
4. Verificar REST catalog en `http://localhost:8181`.

## Comandos completos de testeo

### 1) Smoke automatico

```powershell
powershell -ExecutionPolicy Bypass -File scripts/lakehouse_smoke.ps1
```

### 2) Entrar a spark-sql con catalogo REST

```powershell
docker exec -it bmo_lakehouse_spark spark-sql --driver-memory 512M --conf spark.sql.defaultCatalog=lakehouse --conf spark.sql.catalog.lakehouse=org.apache.iceberg.spark.SparkCatalog --conf spark.sql.catalog.lakehouse.type=rest --conf spark.sql.catalog.lakehouse.uri=http://rest:8181 --conf spark.sql.catalog.lakehouse.warehouse=s3://warehouse/ --conf spark.sql.catalog.lakehouse.io-impl=org.apache.iceberg.aws.s3.S3FileIO --conf spark.sql.catalog.lakehouse.s3.endpoint=http://minio:9000 --conf spark.sql.catalog.lakehouse.s3.path-style-access=true --conf spark.sql.catalog.lakehouse.s3.access-key-id=lakehouse --conf spark.sql.catalog.lakehouse.s3.secret-access-key=lakehouse123 --conf spark.hadoop.fs.s3a.endpoint=http://minio:9000 --conf spark.hadoop.fs.s3a.access.key=lakehouse --conf spark.hadoop.fs.s3a.secret.key=lakehouse123 --conf spark.hadoop.fs.s3a.path.style.access=true --conf spark.hadoop.fs.s3a.connection.ssl.enabled=false
```

Luego dentro de `spark-sql`:

```sql
CREATE NAMESPACE IF NOT EXISTS lakehouse.bronze;
CREATE NAMESPACE IF NOT EXISTS lakehouse.silver;
CREATE NAMESPACE IF NOT EXISTS lakehouse.gold;

CREATE TABLE IF NOT EXISTS lakehouse.bronze.agent_events (
    event_id string,
    event_ts timestamp,
    source string,
    payload string
) USING iceberg
PARTITIONED BY (days(event_ts));

SHOW NAMESPACES IN lakehouse;
SHOW TABLES IN lakehouse.bronze;
SELECT * FROM lakehouse.bronze.agent_events LIMIT 10;
```

### 3) Verificar metadatos Iceberg

```sql
SELECT * FROM lakehouse.bronze.agent_events.history;
SELECT snapshot_id, committed_at, operation FROM lakehouse.bronze.agent_events.snapshots ORDER BY committed_at DESC;
SELECT file_path, file_format, record_count, file_size_in_bytes FROM lakehouse.bronze.agent_events.files;
SELECT * FROM lakehouse.bronze.agent_events.partitions;
```

### 4) Ver logs de cada componente

```bash
docker logs bmo_lakehouse_minio --tail 200
docker logs bmo_lakehouse_minio_init
docker logs bmo_lakehouse_rest --tail 200
docker logs bmo_lakehouse_spark --tail 200
```

### Ejecutar smoke test

```powershell
powershell -ExecutionPolicy Bypass -File scripts/lakehouse_smoke.ps1
```

### Ejecutar smoke sin insertar datos

```powershell
powershell -ExecutionPolicy Bypass -File scripts/lakehouse_smoke.ps1 -InsertSample:$false
```

### Ejecutar smoke con credenciales custom

```powershell
powershell -ExecutionPolicy Bypass -File scripts/lakehouse_smoke.ps1 `
  -MinioUser "TU_USER" `
  -MinioPassword "TU_PASSWORD"
```

## Runbook de comandos (operacion diaria)

### Ciclo de vida

Levantar:

```bash
docker compose -f docker/docker-compose.yml up -d
```

Ver estado:

```bash
docker compose -f docker/docker-compose.yml ps
```

Reiniciar Spark:

```bash
docker compose -f docker/docker-compose.yml restart spark-iceberg
```

Bajar servicios:

```bash
docker compose -f docker/docker-compose.yml down
```

Reset total (incluye datos de MinIO):

```bash
docker compose -f docker/docker-compose.yml down -v
```

### Logs y diagnostico

Logs MinIO:

```bash
docker logs bmo_lakehouse_minio --tail 200
```

Logs minio-init:

```bash
docker logs bmo_lakehouse_minio_init
```

Logs Spark:

```bash
docker logs bmo_lakehouse_spark --tail 200
```

### SQL de validacion rapida

Mostrar namespaces:

```sql
SHOW NAMESPACES IN lakehouse;
```

Mostrar tablas Bronze:

```sql
SHOW TABLES IN lakehouse.bronze;
```

Conteo de filas:

```sql
SELECT count(*) AS total_rows FROM lakehouse.bronze.agent_events;
```

## Como funciona exactamente este Lakehouse

### Flujo tecnico real

1. `minio` provee object storage S3-compatible.
2. `minio-init` crea buckets operativos (`bronze/silver/gold/warehouse`).
3. `spark` inicia con catalogo Iceberg llamado `lakehouse` via REST (`http://rest:8181`) y `warehouse` apuntando a `s3://warehouse/`.
4. Spark crea namespaces y una tabla Iceberg inicial (`lakehouse.bronze.agent_events`).
5. Cada escritura crea un nuevo snapshot Iceberg (no pisa archivos viejos).

## Que garantiza el sistema (Iceberg + Spark + MinIO)

1. Atomicidad de commits: una transaccion se publica completa o no se publica.
2. Snapshot isolation: lectores ven snapshots consistentes sin lecturas parciales.
3. Evolucion de esquema: permite agregar/renombrar columnas con control de metadatos.
4. Time travel: consultas a snapshots/versiones historicas.
5. Optimistic concurrency: evita corrupcion ante escrituras concurrentes.
6. Partition pruning: reduce escaneo leyendo solo archivos relevantes.

## Metadatos: como se manejan

Iceberg mantiene metadatos en el bucket `warehouse` dentro de cada tabla:

1. Metadata file principal (`metadata/vN.metadata.json`): estado actual de la tabla.
2. Manifest list: lista de manifests usados por cada snapshot.
3. Manifest files: inventario de data files, estadisticas min/max, null counts, etc.
4. Data files (Parquet): datos fisicos de cada commit.

En cada write:

1. Spark escribe nuevos Parquet.
2. Iceberg genera manifests + metadata nueva version.
3. Hace commit atomico del puntero a la nueva version.
4. Snapshots viejos quedan disponibles para auditoria/time travel.

### Consultas utiles de metadatos

Historial:

```sql
SELECT * FROM lakehouse.bronze.agent_events.history;
```

Snapshots:

```sql
SELECT snapshot_id, committed_at, operation
FROM lakehouse.bronze.agent_events.snapshots
ORDER BY committed_at DESC;
```

Archivos fisicos:

```sql
SELECT file_path, file_format, record_count, file_size_in_bytes
FROM lakehouse.bronze.agent_events.files;
```

Particiones:

```sql
SELECT * FROM lakehouse.bronze.agent_events.partitions;
```

## Como manejar buckets y capas

### Separacion recomendada

1. `bronze` bucket: landing raw (JSON/CSV/Parquet crudo desde fuentes).
2. `silver` bucket: datos limpios/intermedios fuera de tabla Iceberg si necesitas staging por archivos.
3. `gold` bucket: exports finales o data products publicados por archivo.
4. `warehouse` bucket: exclusivo para tablas Iceberg (data + metadata ACID).

Regla operativa:

1. Si quieres garantias ACID y metadatos gestionados, escribe en tablas Iceberg del catalogo `lakehouse` (que viven en `warehouse`).
2. Si quieres solo staging de archivos, usa `bronze/silver/gold` como object storage plano.

## Como usar la tabla inicial lakehouse.bronze.agent_events

Definicion actual:

- Tabla: `lakehouse.bronze.agent_events`.
- Campos: `event_id`, `event_ts`, `source`, `payload`.
- Particion: `days(event_ts)`.

Implicancias de `days(event_ts)`:

1. Cada dia queda agrupado logicamente para pruning de consultas.
2. Consultas por rango temporal escanean menos archivos.
3. Conviene siempre filtrar por `event_ts` para aprovechar rendimiento.

Insercion ejemplo:

```sql
INSERT INTO lakehouse.bronze.agent_events
VALUES ('evt-1001', current_timestamp(), 'kafka', '{"job_id":"123"}');
```

Consulta por dia:

```sql
SELECT event_id, source, event_ts
FROM lakehouse.bronze.agent_events
WHERE event_ts >= current_date()
ORDER BY event_ts DESC;
```

## Patron de uso recomendado (Bronze -> Silver -> Gold)

1. Bronze:
    - Ingesta raw desde PostgreSQL/Kafka/APIs a archivos en bucket `bronze`.
    - Opcional: cargar esos raw a tablas Iceberg `lakehouse.bronze.*`.
2. Silver:
    - Limpieza, tipado, normalizacion y deduplicacion en `lakehouse.silver.*`.
3. Gold:
    - Agregados de negocio y tablas consumibles por BI/agente en `lakehouse.gold.*`.

## Uso desde Python (guardar y consultar)

### Opcion recomendada: PySpark con el mismo catalogo REST

Usa esta base para escribir y consultar tablas Iceberg desde Python.

```python
from pyspark.sql import SparkSession

spark = (
    SparkSession.builder
    .appName("lakehouse-python")
    .config("spark.sql.defaultCatalog", "lakehouse")
    .config("spark.sql.catalog.lakehouse", "org.apache.iceberg.spark.SparkCatalog")
    .config("spark.sql.catalog.lakehouse.type", "rest")
    .config("spark.sql.catalog.lakehouse.uri", "http://rest:8181")
    .config("spark.sql.catalog.lakehouse.warehouse", "s3://warehouse/")
    .config("spark.sql.catalog.lakehouse.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
    .config("spark.sql.catalog.lakehouse.s3.endpoint", "http://minio:9000")
    .config("spark.sql.catalog.lakehouse.s3.path-style-access", "true")
    .config("spark.sql.catalog.lakehouse.s3.access-key-id", "lakehouse")
    .config("spark.sql.catalog.lakehouse.s3.secret-access-key", "lakehouse123")
    .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000")
    .config("spark.hadoop.fs.s3a.access.key", "lakehouse")
    .config("spark.hadoop.fs.s3a.secret.key", "lakehouse123")
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
    .getOrCreate()
)

# Bootstrap minimo
spark.sql("CREATE NAMESPACE IF NOT EXISTS lakehouse.bronze")
spark.sql("CREATE NAMESPACE IF NOT EXISTS lakehouse.silver")
spark.sql("CREATE NAMESPACE IF NOT EXISTS lakehouse.gold")

# Escritura (guardar informacion)
spark.sql("""
CREATE TABLE IF NOT EXISTS lakehouse.bronze.agent_events (
  event_id string,
  event_ts timestamp,
  source string,
  payload string
) USING iceberg
PARTITIONED BY (days(event_ts))
""")

spark.sql("""
INSERT INTO lakehouse.bronze.agent_events
VALUES ('evt-python-1', current_timestamp(), 'python', '{"ok":true}')
""")

# Consulta (leer informacion)
df = spark.sql("SELECT event_id, source, event_ts FROM lakehouse.bronze.agent_events ORDER BY event_ts DESC LIMIT 20")
df.show(truncate=False)

# Metadatos Iceberg (auditoria)
spark.sql("SELECT committed_at, operation FROM lakehouse.bronze.agent_events.snapshots ORDER BY committed_at DESC").show(truncate=False)
spark.sql("SELECT file_path, record_count FROM lakehouse.bronze.agent_events.files LIMIT 20").show(truncate=False)

spark.stop()
```

### Ejecucion rapida desde el contenedor Spark

Puedes ejecutar Python directamente dentro de `bmo_lakehouse_spark` para no instalar nada local:

```powershell
docker exec -it bmo_lakehouse_spark python
```

Dentro de ese prompt, pega el ejemplo de PySpark anterior.

### Patron Python Bronze -> Silver -> Gold

1. Bronze (raw): escribe eventos crudos en `lakehouse.bronze.*`.
2. Silver (limpieza): lee Bronze, deduplica/normaliza y guarda en `lakehouse.silver.*`.
3. Gold (consumo): agrega metrica de negocio y publica en `lakehouse.gold.*`.

Ejemplo rapido de paso Bronze -> Silver:

```python
bronze_df = spark.table("lakehouse.bronze.agent_events")

silver_df = (
    bronze_df
    .dropDuplicates(["event_id"])
    .withColumnRenamed("payload", "payload_json")
)

silver_df.writeTo("lakehouse.silver.agent_events_clean").using("iceberg").createOrReplace()
```

## Limites actuales de este bootstrap

1. Es entorno local de bootstrap, no hardening productivo.
2. No incluye HA del REST catalog ni TLS interno.
3. No incluye Airflow/dbt aun; este frente queda listo para conectarlos en siguientes pasos.
