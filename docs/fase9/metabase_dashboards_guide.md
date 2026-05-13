# Guía de Dashboards y BI con Metabase

Este documento centraliza la configuración de Metabase para el monitoreo del asistente personal (BMO), incluyendo la instalación de drivers para Oracle y las consultas SQL reales para los dashboards de ingesta y calidad.

---

## 1. Configuración de Conectividad

### 1.1 Habilitar Conector Oracle (JDBC Driver)
Metabase no incluye el driver de Oracle por defecto. Para habilitarlo en el clúster K3s, debemos actualizar el despliegue de Metabase en `k8s/apps-deployment.yaml` para descargar el driver mediante un `initContainer`.

**Modificación necesaria en `apps-deployment.yaml`:**

```yaml
spec:
  template:
    spec:
      initContainers:
      - name: install-oracle-driver
        image: busybox
        command: ["sh", "-c", "wget -O /plugins/ojdbc11.jar https://repo1.maven.org/maven2/com/oracle/database/jdbc/ojdbc11/23.3.0.23.09/ojdbc11-23.3.0.23.09.jar"]
        volumeMounts:
        - name: plugins-volume
          mountPath: /plugins
      containers:
      - name: metabase
        # ... resto de la config ...
        volumeMounts:
        - name: plugins-volume
          mountPath: /plugins
      volumes:
      - name: plugins-volume
        emptyDir: {}
```

### 1.2 Conexión a Trino (Lakehouse Iceberg)
*   **Host**: `trino.personal-ai.svc.cluster.local`
*   **Puerto**: `8080`
*   **Catálogo**: `iceberg`
*   **Usuario**: `admin`

---

## 2. Dashboard de "Salud de la Ingesta" (App DB - Oracle)

Estas consultas deben ejecutarse contra la conexión de **Oracle**, que contiene el estado operacional de los documentos.

### 2.1 Ranking de Estrategias (Eficiencia)
**SQL (Oracle):**
```sql
SELECT 
    strategy, 
    ROUND(AVG(processing_time), 2) AS avg_time_sec,
    COUNT(*) AS total_docs
FROM ingestion_status
WHERE strategy IS NOT NULL
GROUP BY strategy
ORDER BY avg_time_sec ASC
```

### 2.2 Nube de Reportes (Últimas Ingestas)
**SQL (Oracle):**
```sql
SELECT * FROM (
    SELECT 
        updated_at AS fecha,
        source_path AS archivo,
        report AS resumen_ia,
        chunks_count AS chunks
    FROM ingestion_status
    WHERE status = 'indexed'
    ORDER BY updated_at DESC
) WHERE ROWNUM <= 20;
```

### 2.3 Histograma de Chunks
**SQL (Oracle):**
```sql
SELECT 
    chunks_count, 
    COUNT(*) AS cantidad_documentos
FROM ingestion_status
WHERE status = 'indexed'
GROUP BY chunks_count
ORDER BY chunks_count ASC
```

---

## 3. Monitor de Calidad RAG (Lakehouse - Trino)

Estas consultas deben ejecutarse contra la conexión de **Trino**, leyendo directamente de las capas Gold de Iceberg generadas por dbt.

### 3.1 Evolución Temporal (Calidad Diaria)
**SQL (Trino):**
```sql
SELECT 
    run_day AS date, 
    AVG(answer_relevancy) AS avg_relevancy, 
    AVG(faithfulness) AS avg_faithfulness 
FROM iceberg.gold.fact_evaluations 
WHERE status = 'success'
GROUP BY run_day
ORDER BY run_day ASC
```
*   **Tip Visual**: En Metabase, fija el eje Y de 0 a 1 para evitar que fluctuaciones pequeñas parezcan críticas.

Usa avg_relevancy y avg_faithfulness para medir la calidad de un muestra aleatoria de runs del agente.

### 3.2 Monitoreo de Costos (LLM Costs)
**SQL (Trino):**
```sql
SELECT 
    day, 
    SUM(total_cost_usd) AS total_cost,
    model_name
FROM iceberg.gold.fact_llm_costs 
GROUP BY day, model_name
ORDER BY day DESC
```

### 3.3 Correlación Calidad vs Estrategia de Ingesta
Esta consulta requiere unir datos de Oracle (ingesta) con Trino (evaluación). Si no tienes las tablas federadas, dbt debe haber consolidado `ingestion_status` en el Lakehouse.

**SQL (Trino):**
```sql
SELECT 
    i.strategy, 
    AVG(e.faithfulness) AS avg_faithfulness,
    AVG(e.answer_relevancy) AS avg_relevancy
FROM iceberg.gold.fact_evaluations e
JOIN iceberg.gold.ingestion_status i ON e.doc_id = i.doc_id
WHERE i.strategy IS NOT NULL
GROUP BY i.strategy
```

---

## 4. Exploración Directa (Chunks en tiempo real)

**SQL (Trino):**
```sql
SELECT 
    created_at,
    doc_id,
    content, 
    metadata 
FROM iceberg.gold.document_chunks
ORDER BY created_at DESC
LIMIT 20
```
*   **Visualización**: Tabla con formato JSON habilitado para la columna `metadata`.


## Dashboad
Con todas estas preguntas luego cree un dashboard de BMO con todas las preguntas/tablas para poder chequearlas.'




## Reales ahora

¡Entendido! Vamos a enfocarnos 100% en el Lakehouse (Trino) usando esas 3 tablas maestras. Estas son las preguntas "de oro" que te darán una visión total del rendimiento de BMO.

He actualizado la guía en docs/fase9/metabase_dashboards_guide.md con estas nuevas consultas, eliminando por ahora lo de Oracle para que te centres en los datos de Iceberg.

Preguntas sugeridas para tu Dashboard "BMO Analytics":
1. Sección de Calidad (Basada en fact_evaluations)
KPI: Calidad Media Total: El promedio de faithfulness y answer_relevancy (formato: "Number").
Evolución de Calidad: Gráfico de líneas por run_day.
Tabla de "Runs Problemáticos": Una lista de los runs donde faithfulness < 0.6, mostrando la columna faithfulness_reason. ¡Esto es oro puro para debuguear por qué el agente alucina!
2. Sección de Costos y Uso (Basada en fact_llm_costs)
Gasto por Modelo: Un gráfico de torta (Pie chart) que muestre cuánto dinero se lleva cada modelo (GPT-4, Llama 3, etc.).
Consumo de Tokens Diario: Gráfico de áreas para ver picos de uso del asistente.
3. Sección de Performance (Basada en fact_agent_performance)
Latencia Promedio: ¿Cuánto tarda BMO en responder? (Gráfico de líneas).
Correlación Latencia vs Tokens: Un gráfico de dispersión (Scatter plot) para ver si los documentos más largos hacen que el agente sea mucho más lento.
Actualización del Documento
Aquí tienes el contenido actualizado para docs/fase9/metabase_dashboards_guide.md:

Este dashboard consume directamente las tablas Gold de **Apache Iceberg** a través de **Trino**.
## 1. KPIs Principales (Números)
### 1.1 Fidelidad Promedio (Faithfulness)
```sql
SELECT AVG(faithfulness) FROM iceberg.gold.fact_evaluations WHERE evaluation_state = 'evaluated'
1.2 Costo Total Acumulado (USD)
sql
SELECT SUM(total_cost_usd) FROM iceberg.gold.fact_llm_costs

2. Gráficos de Tendencia
2.1 Calidad del Agente vs Tiempo
Visualización: Line Chart.

sql
SELECT 
    run_day, 
    AVG(answer_relevancy) as relevancy, 
    AVG(faithfulness) as faithfulness 
FROM iceberg.gold.fact_evaluations 
GROUP BY run_day 
ORDER BY run_day ASC
2.2 Latencia del Agente (ms)
Visualización: Line Chart.

sql
SELECT 
    date_trunc('day', start_time) as day, 
    AVG(latency_ms) as avg_latency 
FROM iceberg.gold.fact_agent_performance 
GROUP BY 1 
ORDER BY 1 ASC



Gráfico 1: Volumen y Estabilidad (Barras Apiladas)
Este gráfico te dirá de un vistazo cuánto tráfico tuviste y cuántos fallaron.

Consulta: La misma que ya tienes.

Visualización: Gráfico de barras (Bar chart).

Configuración: * Eje X: run_day

Eje Y: Añade dos métricas: success_runs y error_runs.

Display: Ve a las opciones de visualización (el ícono de engranaje) y selecciona "Stack" (Apilar). Esto pondrá los errores encima de los aciertos, mostrándote el volumen total (run_count) y la proporción visual de fallos. Podés ponerle color rojo a los errores y verde/azul a los aciertos.

Gráfico 2: Tasa de Éxito (Línea de Tendencia)
Este gráfico aísla la calidad de tus ejecuciones.

Consulta: La misma. (Tip de Metabase: Guarda la Pregunta 1, dale a "Duplicar", y solo cambia el gráfico).

Visualización: Gráfico de líneas (Line chart) o Área.

Configuración:

Eje X: run_day

Eje Y: success_rate

Ajuste Crítico: En las opciones del Eje Y, desactiva el escalado automático y fuerza el Mínimo a 0 y el Máximo a 1. Así tendrás un porcentaje real (0% a 100%).

Gráfico 3: Monitor de Rendimiento / Latencia (Líneas Múltiples)
Aquí monitoreas qué tan rápido está respondiendo el agente.

Consulta: La misma.

Visualización: Gráfico de líneas (Line chart).

Configuración:

Eje X: run_day

Eje Y: Añade avg_latency_ms y max_latency_ms (puedes omitir la mínima si no te aporta mucho valor).

Display: Usa una escala logarítmica si los picos del máximo te aplastan el promedio, o simplemente déjalo normal.

3. Análisis Detallado (Debug & Costos)
3.1 ¿Por qué alucina el agente? (Tabla de Razones)
Visualización: Table.

sql
SELECT 
    run_day, 
    user_id, 
    faithfulness, 
    faithfulness_reason 
FROM iceberg.gold.fact_evaluations 
WHERE faithfulness < 0.6 
ORDER BY run_day DESC
3.2 Reparto de Costos por Modelo
Visualización: Pie Chart.

sql
SELECT 
    model_name, 
    SUM(total_cost_usd) as cost 
FROM iceberg.gold.fact_llm_costs 
GROUP BY model_name
3.3 Top Usuarios por Consumo (Tokens)
Visualización: Bar Chart.

sql
SELECT 
    user_id, 
    SUM(total_tokens) as tokens 
FROM iceberg.gold.fact_llm_costs 
GROUP BY user_id 
ORDER BY tokens DESC