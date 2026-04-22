# ETL y Orquestación del Lakehouse

## 1. Qué corre en cada lugar

Sí: hoy tienes **dos procesos Spark** en la práctica, pero no son dos lakehouses distintos.

1. `spark-iceberg` en [docker/docker-compose.yml](../../docker/docker-compose.yml)
   - Es el Spark del Lakehouse para exploración, notebooks y SQL interactivo.
   - Vive junto a MinIO y el REST catalog.
   - Lo usas para inspección manual, pruebas puntuales y para validar Iceberg.

2. `spark-thrift` en [data_tooling/docker-compose.spark-airflow.yml](../../data_tooling/docker-compose.spark-airflow.yml)
   - Es el Spark que consume Airflow y dbt.
   - Expone un Thrift Server en `10000`.
   - No reemplaza al otro Spark: lo complementa para orquestación.

La forma correcta de pensarlo es esta:

- Un Spark para el Lakehouse operativo/interactivo.
- Otro Spark para el pipeline de datos.
- Ambos apuntan al mismo MinIO y al mismo catálogo Iceberg.

## 2. Por qué separarlo así

1. Evitas mezclar debugging manual con jobs automatizados.
2. Puedes reiniciar Airflow/dbt sin tocar el entorno del Lakehouse.
3. Mantienes más clara la frontera entre infraestructura de datos y orquestación.
4. Cuando más adelante quieras mover todo a Kubernetes, la separación ya va a estar explícita.

## 3. Cómo funciona dbt con Spark en este proyecto

dbt no procesa datos por sí mismo. En este setup:

1. dbt genera SQL.
2. Ese SQL se envía a Spark Thrift.
3. Spark ejecuta el trabajo pesado.
4. Iceberg escribe en MinIO.

### El truco del esquema en dbt

Por defecto dbt puede concatenar el esquema base con el esquema del modelo. En un proyecto medallón eso suele romperse y terminar en nombres raros como `bronze_silver`.

Para evitarlo, este proyecto usa el macro `generate_schema_name.sql` para que:

1. Si el modelo no define esquema, use el esquema base del profile.
2. Si el modelo define `+schema: silver` o `+schema: gold`, lo respete tal cual.

Eso hace que Bronze, Silver y Gold queden exactamente donde esperas.

## 4. El flujo ETL que vas a probar

### Bronze

- Fuente: CSV de LangSmith o export de MLflow.
- Objetivo: guardar los datos crudos sin perder trazabilidad.
- Tabla: `lakehouse.bronze.raw_llm_traces`.

### Silver

- Objetivo: limpiar, castear, normalizar y separar anomalías.
- Tabla principal: `lakehouse.silver.stg_agent_runs`.
- Tabla de anomalías: `lakehouse.silver.stg_agent_run_anomalies`.

### Gold

- Objetivo: dejar métricas listas para consumo.
- `fact_llm_costs`: costo y tokens por día y usuario.
- `fact_agent_performance`: latencia y tasa de éxito.
- `fact_evaluations`: resultados de DeepEval o base preparada para cruzarlos después.

## 5. Orden recomendado de implementación

1. Ingestar Bronze.
2. Validar `stg_agent_runs`.
3. Separar anomalías.
4. Crear fact costs.
5. Crear fact performance.
6. Dejar listo fact evaluations como puente para DeepEval.

## 6. Qué conviene recordar

1. No estás duplicando infraestructura innecesariamente: estás separando responsabilidades.
2. El Spark del Lakehouse no es “el de Airflow” ni al revés.
3. Airflow solo orquesta.
4. dbt solo compila y envía SQL.
5. Spark ejecuta.
6. Iceberg versiona y MinIO persiste.
