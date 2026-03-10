# Asistente de Conocimiento Personal (Personal AI Assistant)

Un asistente personal de IA basado en la arquitectura **Self-RAG** (Retrieval-Augmented Generation) y **LangGraph**. Diseñado para procesar, indexar inteligencialmente y recuperar conocimiento a partir de tus documentos personales. Este proyecto evoluciona desde un prototipo local hacia un sistema robusto, escalable y preparado para la nube (AWS), apoyándose fuertemente en patrones de diseño como Inyección de Dependencias (Factory Pattern) para facilitar el cambio entre infraestructura local y cloud-native.

## 🚀 Estado Actual del Proyecto

Actualmente hemos **finalizado la Fase 1**. El sistema es completamente funcional en un entorno local y dockerizado.

**Características implementadas:**
- **Pipeline de Ingesta Universal:** Usa `MarkItDown` para normalizar documentos complejos (PDF, DOCX) manteniendo su jerarquía semántica.
- **Indexación Incremental:** Utiliza `SQLRecordManager` (PostgreSQL) para evitar procesamiento redundante de chunks idénticos.
- **Enrutamiento y Chunking Adaptativo:** `ChunkingRouter` que decide entre un troceado jerárquico o un *Agentic Chunker* semántico según el documento.
- **Agente Self-RAG con LangGraph:** Implementación de nodos que evalúan los documentos recuperados y previenen alucinaciones. Incluye validadores estructurados JSON, políticas de reintento (`RetryPolicy`) y *fallbacks* automáticos entre modelos (ej. Gemini a GPT-4o-mini).
- **Memoria y Checkpoints:** Persistencia de hilos de conversación usando `PostgresSaver`. Nodos condicionales de compresión de historial (Summarization) para optimizar contexto.
- **Testing y CI/CD:** Pruebas de integración automatizadas usando `Testcontainers` para levantar ChromaDB efímeros en flujos de GitHub Actions.

---

## 🗺️ Fases de Desarrollo

*   ✅ **Fase 1: Cimientos y RAG Inteligente Local** (¡Completada!)
    *   Setup de FastAPI, ChromaDB, Providers (Gemini/OpenAI) gestionados por Factories.
    *   PostgreSQL para persistencia de LangGraph y RecordManager.
*   ⏳ **Fase 2: Asincronía y Escalabilidad (Workers)** (Pendiente)
    *   Integración de RabbitMQ, Celery y Redis para delegar la ingesta asíncrona pesada.
*   ⏳ **Fase 3: Ingesta Robusta de Datos y GraphRAG** (Pendiente)
    *   Apache Kafka para flujos de datos complejos y Neo4j/OpenSearch para grafos de conocimiento.
*   ⏳ **Fase 4: Orquestación y Memoria en la Nube** (Pendiente)
    *   Migración de checkpointers y storage hacia soluciones administradas como DynamoDB Aura.
*   ⏳ **Fase 5: Despliegue Cloud-Native y Observabilidad** (Pendiente)
    *   Alistamiento para AWS EKS (Kubernetes), OpenTelemetry y despliegue por componentes.
*   ⏳ **Fase 6: Evaluación Continua** (Pendiente)
    *   Test de calidad avanzados utilizando DeepEval.

---

## 📂 Estructura del Proyecto

```text
├── docker/                 # Configuración de contenedores (docker-compose, Dockerfiles)
├── docs/                   # Documentación extensa (Resúmenes, decisiones y guías por fase)
│   └── fase1/              # Detalles técnicos de la Fase 1 (API, Chunking, Testcontainers)
├── postman/                # Colecciones para pruebas de endpoints
├── src/                    # Código fuente
│   ├── api/                # Endpoints y enrutadores de FastAPI
│   ├── core/               # Lógica de Agentes LangGraph, Prompts, GraphStates
│   ├── providers/          # Patrón Factory: Abstracciones de base de datos y LLMs
│   │   ├── checkpointer/   # Implementación PostgreSQL Saver
│   │   ├── llm/            # Clientes LLM (Gemini, Mistral, OpenAI)
│   │   ├── record_manager/ # Implementación de SQLRecordManager
│   │   └── vector_store/   # Clientes Vectoriales (Chroma, etc.)
│   ├── schemas/            # Pydantic models para Request/Responses y lógica interna
│   └── tests/              # Pruebas Unitarias e Integración (Pytest + Testcontainers)
├── .env.example            # Plantilla de configuración de entorno
├── .gitignore              # Archivos y carpetas ignoradas (/src/tests/__pycache__, etc)
├── pytest.ini              # Configuración de recolección de pruebas asíncronas
└── requirements.txt        # Dependencias principales del proyecto
```

---

## 💻 Instrucciones de Uso Rápido

### Prerrequisitos
Asegúrate de contar con Python 3.12 y tener Docker corriendo en tu sistema.

### 1. Levantar la Infraestructura Local
```bash
docker compose up -d
```
Esto levantará los contenedores necesarios, que incluyen la API (FastAPI), la base de datos PostgreSQL y la base de datos vectorial Chroma.

### 2. Entorno y Dependencias
Recomendamos el uso de un entorno virtual (idealmente con `uv` o directamente con `python -m venv`):
```bash
# Crear y activar entorno virtual
python -m venv .venv
# (En Windows)
.venv\Scripts\activate

# Instalar los requerimientos
pip install -r requirements.txt
```

Luego de esto, puedes usar las colecciones provistas en `/postman` para interactuar con los endpoints de ingesta (`/api/ingest`) y consulta (`/api/query`).

**Nota de Pruebas:** Para ejecutar los tests localmente usando Testcontainers y los mocks incorporados:
```bash
python -m pytest src/tests/
```
