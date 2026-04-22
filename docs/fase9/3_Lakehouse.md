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

1. El Catálogo (Catalog)
Qué es: Es el "Índice principal" o el "Registro de la propiedad". El Catálogo no guarda los datos físicos ni los archivos Parquet; su único trabajo es saber dónde está la última versión (snapshot) de cada tabla.

Por qué es vital: Si dos procesos de Spark intentan hacer un INSERT al mismo tiempo en la misma tabla, el Catálogo actúa como el árbitro. Permite que uno escriba y hace que el otro espere o reintente, evitando que tus datos se corrompan.

En Spark: Cuando configuras --conf spark.sql.catalog.lakehouse=org.apache.iceberg.spark.SparkCatalog, le estás diciendo a Spark: "He creado un catálogo de Iceberg y lo he bautizado como lakehouse".

Tu implementación: En la arquitectura moderna, usaste un REST Catalog. Esto significa que cuando Spark quiere saber dónde está una tabla, no busca a ciegas en el almacenamiento, sino que le hace una petición HTTP GET a tu servicio REST, y este le responde con la ruta exacta en MinIO.

2. El Espacio de Nombres (Namespace)
Qué es: Es una agrupación lógica de tablas. Si vienes del mundo de las bases de datos relacionales (como PostgreSQL o MySQL), un Namespace es exactamente lo mismo que un "Schema" o una "Database".

Por qué es vital: Sirve para organizar tus datos por dominios de negocio, capas de madurez o equipos, aplicando reglas de acceso o cuotas a nivel de grupo.

Tu implementación: Cuando ejecutas CREATE NAMESPACE IF NOT EXISTS lakehouse.bronze;, estás creando una "carpeta lógica" llamada bronze dentro del catálogo lakehouse. Al tener bronze, silver y gold, estás usando los Namespaces para separar la calidad y el refinamiento de tus datos.

3. La Tabla (Table)
Qué es: Es la entidad final que contiene el esquema (nombres de columnas y tipos de datos) y la historia completa de los registros.

Por qué es vital en Iceberg: A diferencia de una base de datos normal, una tabla Iceberg es en realidad un "árbol" de archivos físicos en tu almacenamiento (MinIO). Cuando creas una tabla, Iceberg genera:

Archivos de Datos: Los verdaderos archivos .parquet con la información.

Archivos Manifest: Archivos que hacen un inventario de qué archivos Parquet pertenecen a qué partición.

Archivos de Metadata: Archivos .json que guardan el esquema de la tabla y la historia de todas las modificaciones (snapshots).

Tu implementación: agent_events o llm_telemetry son tus tablas. Contienen la definición de qué columnas existen (ej. run_id, latency_ms) y apuntan a los archivos físicos en tu bucket de MinIO.


Para responderte directamente: Tal como está configurado tu Spark en este momento, no estás usando los buckets bronze, silver ni gold de MinIO para tus tablas Iceberg. Todo está yendo a parar al bucket warehouse.

Vamos a desglosar por qué pasa esto, cómo se conectan los conceptos y qué deberías hacer con esos buckets extra.

La Configuración Clave: El warehouse
En tu script de PySpark (y en tu docker-compose), le pasaste esta configuración a Spark:
--conf spark.sql.catalog.lakehouse.warehouse=s3://warehouse/

Esa línea es la regla maestra. Le dice a Iceberg: "Absolutamente todo lo que yo cree en el catálogo lakehouse debe vivir físicamente dentro del bucket de MinIO llamado warehouse".

Por lo tanto, la traducción de Iceberg a MinIO funciona así:

Catálogo (lakehouse) -> Apunta al bucket raíz: s3://warehouse/

Namespace (bronze) -> Iceberg crea una carpeta dentro del bucket: s3://warehouse/bronze/

Tabla (llm_telemetry) -> Iceberg crea una subcarpeta: s3://warehouse/bronze/llm_telemetry/

Archivos Físicos -> Dentro de esa subcarpeta, Iceberg crea las carpetas /data (para tus .parquet) y /metadata (para tus .json).

Entonces, ¿para qué creaste los buckets bronze, silver y gold en MinIO?
Esto nos lleva a las dos arquitecturas estándar de la industria. Tú creaste la infraestructura para la Arquitectura 2, pero configuraste Spark para la Arquitectura 1.

Arquitectura 1: Un solo bucket ("El Data Lake Unitario") - Lo que tienes ahora
Todo vive en el bucket warehouse.

Las capas (bronze, silver) son simplemente carpetas (namespaces en Iceberg) dentro de ese bucket.

Ventaja: Es muchísimo más fácil de gestionar, respaldar (backups) y configurar permisos, ya que solo te preocupas de un bucket.

Arquitectura 2: "Un Bucket por Capa" - Para lo que creaste los buckets
En esta arquitectura, quieres que la tabla lakehouse.bronze.datos se guarde en el bucket s3://bronze/, y la tabla lakehouse.silver.datos en s3://silver/.

Para lograr esto en Iceberg, no usas una regla global warehouse. En su lugar, cuando creas el namespace con SQL, le dices explícitamente a dónde apuntar:

SQL
CREATE NAMESPACE lakehouse.bronze LOCATION 's3://bronze/';
CREATE NAMESPACE lakehouse.silver LOCATION 's3://silver/';
¿Qué te recomiendo hacer? (La mejor práctica)
Quédate con la Arquitectura 1 (Todo en warehouse). Es el estándar moderno porque AWS S3 y MinIO manejan millones de carpetas dentro de un solo bucket sin problemas de rendimiento.

Pero entonces, ¿qué haces con los buckets bronze, silver y gold vacíos que creaste en tu script mc mb?

Úsalos como Landing Zones (Zonas de aterrizaje).

Iceberg es un formato estructurado. No puedes simplemente "arrastrar y soltar" un CSV crudo dentro de una tabla Iceberg. Necesitas un lugar físico donde dejar la basura cruda antes de que Spark la lea.

El Flujo Perfecto:

Airflow (o tú a mano): Descarga el langsmith_metrics_export.csv y lo sube físicamente al bucket s3://bronze/archivos_crudos/. (Esto es un simple archivo, no es Iceberg).

Spark: Lee el CSV usando spark.read.csv("s3a://bronze/archivos_crudos/langsmith.csv").

Spark: Limpia el archivo y lo guarda en Iceberg usando df.writeTo("lakehouse.bronze.llm_telemetry")....

MinIO: Iceberg guarda los archivos resultantes .parquet dentro del bucket s3://warehouse/bronze/llm_telemetry/.

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
     dags/
        pipeline_llm_telemetry.py      # Orquestacion: fuente -> bronze -> silver -> gold
     tasks/
        ingest_bronze.py               # Carga cruda del CSV o MLflow hacia Iceberg
- MinIO para almacenamiento de objetos.
- Spark (imagen Tabular) para procesamiento y notebooks.
  dbt_project.yml                  # Configuracion principal de dbt
  models/
     bronze/
     silver/
     gold/
## Como levantar
     bronze/
     silver/
     gold/
     warehouse/
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

## Probar el datalake con CSV o MLflow

Antes de conectar la fuente real de MLflow, la forma mas segura de validar el flujo es simular la ingesta con un CSV exportado de LangSmith o con una extraccion minima de runs de MLflow.

La idea es probar el recorrido completo sin escribir todavia el DAG ni los modelos finales:

1. Fuente de prueba.
    - CSV con trazas de LLM.
    - O una exportacion simple de MLflow con los campos basicos de cada run.
2. Bronze.
    - Cargar los datos crudos en `lakehouse.bronze.raw_llm_traces` o `lakehouse.bronze.llm_traces`.
    - No normalizar demasiado en este paso.
3. Silver.
    - Limpiar tipos, parsear fechas, separar tags y detectar errores.
4. Gold.
    - Generar agregados de negocio para analitica y visualizacion.

### Esqueleto del flujo que vas a implementar mas adelante

```text
airflow/
  dags/
     pipeline_llm_telemetry.py      # Orquestacion: fuente -> bronze -> silver -> gold
  tasks/
     ingest_bronze.py               # Carga cruda del CSV o MLflow hacia Iceberg

dbt/
  dbt_project.yml                  # Configuracion principal de dbt
  models/
     bronze/
        sources.yml                  # Definicion de la fuente cruda
     silver/
        stg_agent_runs.sql           # Limpieza y tipado
     gold/
        fact_llm_costs.sql           # Agregados de costos y tokens
        fact_agent_performance.sql   # Latencia y success rate
        fact_evaluations.sql         # Evaluaciones cruzadas con DeepEval
```

### Que haria cada capa en esa prueba

Bronze:

- Guardar cada fila tal como llega desde el CSV o desde MLflow.
- Conservar columnas como `run_id`, `start_time`, `latency_ms`, `status`, `user_id`, `prompt_tokens`, `completion_tokens`, `tags`.
- Si hace falta, solo aplicar cambios minimos de formato para que Iceberg lo reciba sin romperse.

Silver:

- Convertir `start_time` a `TIMESTAMP`.
- Normalizar `tags` para extraer el tipo de test o convertirlas en array.
- Separar registros fallidos en una tabla de anomalías.

Gold:

- `fact_llm_costs`: costo diario y tokens por usuario.
- `fact_agent_performance`: latencia promedio y tasa de exito.
- `fact_evaluations`: unir runs con puntajes de evaluacion externa.

### Como simular la ingesta analitica con Airflow

La version inicial del DAG puede pensar en 3 pasos, aunque todavia no lo escribamos:

1. Extraer.
    - Consultar MLflow o leer el CSV.
    - Filtrar solo runs terminados o datos relevantes.
2. Cargar a Bronze.
    - Escribir en Iceberg usando Spark.
    - Mantener el schema lo mas cercano posible a la fuente.
3. Transformar con dbt.
    - Ejecutar Silver y Gold sobre las tablas Bronze.

### Guardrails para que Spark no explote por memoria

Si la prueba crece, Spark puede derramar a disco en vez de romperse. Para ese escenario conviene fijar limites desde el inicio:

1. `spark.executor.memory=2g`
    - Limita la RAM disponible por executor.
2. `spark.memory.fraction=0.8`
    - Reserva memoria de trabajo y deja margen para el sistema.
3. `spark.sql.shuffle.partitions=200`
    - Parte las transformaciones pesadas en fragmentos mas chicos.

En esta fase de prueba no hace falta tunear al maximo; solo dejar documentado que el flujo real deberia usar estas defensas cuando empiece a crecer.

### Estructura minima recomendada del proyecto

```text
repo/
  airflow/
     dags/
        pipeline_llm_telemetry.py
     tasks/
        ingest_bronze.py
  dbt/
     dbt_project.yml
     models/
        bronze/
        silver/
        gold/
  lakehouse/
     bronze/
     silver/
     gold/
     warehouse/
```

No hace falta crear todavia los archivos `pipeline_llm_telemetry.py`, `ingest_bronze.py` ni los modelos de dbt. La idea es dejar definida la forma del flujo para implementarlo despues con menos friccion.

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

## Probar el datalake

Si usamos MLflow (o el CSV de LangSmith) como fuente, así se estructurarían tus capas en el Lakehouse usando dbt:
🥉 Capa Bronze (Datos Crudos)
Aquí guardas los datos tal como salen de la API de MLflow o tu CSV, sin alterar nada.
Tabla: lakehouse.bronze.raw_llm_traces
Datos: Run ID, Start Time, Latency (ms), Status, User ID, Prompt Tokens, Completion Tokens, Tags.
🥈 Capa Silver (Staging / Limpieza con dbt)
Aquí usas dbt (o Spark) para limpiar la basura, parsear fechas y castear tipos de datos.
Tabla: lakehouse.silver.stg_agent_runs
Transformaciones: * Convertir Start Time de string a TIMESTAMP.
Limpiar la columna Tags (que en tu CSV viene como "stress_test_v1, agent_generation") para convertirla en un array o extraer el tipo de test.
Filtrar los registros donde Status = 'error' a una tabla de anomalías.
🥇 Capa Gold (Negocio / Modelos Finales con dbt)
Tablas agregadas y listas para el consumo visual.
Tabla 1: fact_llm_costs: Agrupación diaria del Total Cost ($) y tokens por User ID.
Tabla 2: fact_agent_performance: Latencia promedio (Latency (ms)) y tasa de éxito (Success Rate).
Tabla 3: fact_evaluations: Si corres DeepEval de noche, cruzas el Run ID con el puntaje de Faithfulness o Answer Relevancy.

Hay que usar el csv con airflow para correr una prueba en la cual primero se carga el csv con alguna modificacion minima si necesaria en bronze, simula el luego traerse o mandar los datos desde el bucket de mlflow a bronze:Ingesta Analítica (Airflow): Aquí es donde entra tu DAG. Airflow debe:
Consultar la API/DB de MLflow para obtener los IDs de los runs terminados.
Copiar esos datos (o transformarlos ligeramente) hacia lakehouse.bronze.llm_traces en el formato Iceberg que ya probaste.
Ventaja: Esto te permite tener una Única Fuente de Verdad (MLflow) para debuggear, pero un Lakehouse limpio y optimizado para analítica masiva en Metabase.

Que luego ademas va generar la tabla silver y gold con dbt.

