# Generar datos con los checkpoints

## 1. La Arquitectura Medallón (Concepto)

Imagina tu Lakehouse o tu esquema analítico en Aiven PostgreSQL dividido en tres zonas lógicas:

🥉 Bronze (Raw / Crudo): Los datos tal cual llegaron. Historiales crudos de LangGraph en JSON, registros de Kafka sin procesar. Regla: Nunca se altera esta capa.

🥈 Silver (Staging / Limpieza): Tablas normalizadas. Se limpian valores nulos, se extraen campos de los JSON (thread_id, user_id), se estandarizan zonas horarias y se unifican formatos.

🥇 Gold (Core / Analítica): Modelos de negocio finales. Diseñados en un "Modelo Estrella" (Hechos y Dimensiones) listos para que tu agente los consulte con Text-to-SQL o para visualizarlos en Metabase sin que tarden 10 minutos en cargar.

### El Modelo Estrella (Star Schema)
El Modelo Estrella (Star Schema) es una técnica de modelado dimensional que organiza datos en un Data Warehouse usando una tabla de Hechos central (métricas) rodeada de tablas de Dimensiones (contexto), optimizando la velocidad de consultas. Es el enfoque estándar recomendado para BI y herramientas como Power BI por su simplicidad y eficiencia.

1. Tabla de Hechos (Centro): Almacena datos numéricos cuantificables, transaccionales y detallados, tales como "monto de venta", "cantidad vendida" o "beneficios".

2. Tablas de Dimensiones (Puntas): Contienen atributos descriptivos que contextualizan los hechos, tales como productos, clientes, fechas o ubicaciones geográficas. 

Ejemplos de Uso:
Ventas: Una tabla central de "Ventas" unida a dimensiones de "Producto", "Cliente", "Tiempo" y "Sucursal".
Logística: Tabla central de "Envíos" conectada a dimensiones de "Vehículo", "Destino", "Fecha de envío" y "Tipo de carga".

## 2. Estructura del Proyecto dbt
models/
├── bronze/
│   └── src_postgres.yml        # Definición de tus tablas origen
├── silver/
│   ├── stg_logs.sql            # Limpieza de historiales de LangGraph
│   └── stg_ingestion_jobs.sql  # Limpieza de la tabla de ingestas
└── gold/
    ├── dim_tools.sql           # Dimensión de herramientas
    ├── fact_agent_interactions.sql # Hechos: Métricas de cada charla
    └── fact_ingestion_jobs.sql # Hechos: Métricas de documentos

## 3. Detalle de los Modelos (Cómo funcionan)

### Capa Silver: Staging (stg_)
El objetivo aquí no es hacer cálculos complejos, sino "aplanar" y tipar correctamente los datos. Si LangGraph guarda un chorizo de texto JSON en una columna, aquí lo desarmas usando las funciones JSON nativas de tu base de datos.

Valor: Si mañana LangGraph cambia la estructura de su JSON, solo modificas este archivo. La capa Gold ni se entera.

### Capa Gold

#### Capa Gold: Dimensiones (dim_)
Las dimensiones son los "catálogos". Contienen los atributos por los cuales vas a querer filtrar o agrupar tus datos (ej. "Quiero ver los costos por herramienta").

#### Capa Gold: Tablas de Hechos (fact_)
Las tablas de hechos son el corazón analítico. Guardan eventos medibles (métricas) y se conectan a las dimensiones mediante claves (keys).

Modelo: fact_agent_interactions.sql
Este modelo cuenta la historia de cada ejecución de tu agente.

Modelo: fact_ingestion_jobs.sql
Tomando la tabla de ingestas que gestiona tu orquestador de Celery/Kafka.

## 4. ¿Por qué esto es brutal para tu CV y tu Asistente?
Linaje y Documentación: dbt genera automáticamente un grafo visual (un DAG) que muestra que fact_agent_interactions depende de stg_logs y dim_tools. Además, genera una página web documentando cada columna. Esto es Data Engineering puro.

Mitigación de Alucinaciones: Cuando le digas a tu agente "Haz un gráfico de barras con el costo por herramienta del último mes", no le vas a dar acceso a la tabla cruda en PostgreSQL. Le das acceso solamente a las tablas fact_ y dim_ de tu esquema Gold. Al ser esquemas limpios, descriptivos y sin JSON anidados complejos, el LLM generará consultas SQL perfectas al primer intento.

Calidad de Datos (Testing): dbt te permite agregar tests en un YAML (ej. afirmar que total_tokens nunca puede ser negativo o nulo). Si el test falla, dbt aborta la actualización de la capa Gold, evitando que métricas corruptas lleguen a tus dashboards.