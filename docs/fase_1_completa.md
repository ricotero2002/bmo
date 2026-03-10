# Documentación Completa: Fase 1 - Asistente de IA Personal

Este documento consolida todas las decisiones arquitectónicas, implementaciones técnicas y guías de uso desarrolladas durante la **Fase 1** del proyecto del Asistente de Conocimiento Personal.

---

## 1. El Problema y la Solución Propuesta

**El Problema:** A lo largo del tiempo, generamos y guardamos información valiosa que queda fragmentada y aislada en múltiples repositorios. Los métodos tradicionales de búsqueda basados en palabras clave son insuficientes para recuperar información con contexto o descubrir patrones.
**Impacto:** Pérdida de conocimiento útil y tiempo invertido buscando datos específicos en distintas plataformas.

**La Solución:** Un Asistente de Conocimiento Personal basado en Inteligencia Artificial. Utiliza una arquitectura **Self-RAG (Retrieval-Augmented Generation)** fundamentada en **LangGraph** para no solo recuperar texto vectorizado, sino reflexionar sobre él, entender relaciones y generar planes de acción o respuestas exactas.

---

## 2. Decisiones de Ecosistema e Infraestructura

*   **Versión de Python (3.12):** Se seleccionó Python 3.12 como el entorno ideal para 2026. Brinda compatibilidad con la Capa Gratuita de AWS Lambda (que depreca 3.9), cuenta con soporte óptimo para clientes vectoriales modernos, y mejoras masivas de rendimiento en `asyncio` y gestión de memoria, crucial para FastAPI y validaciones de seguridad (Guardrails).
*   **FastAPI & Arquitectura Modular:** La API se estructuró separando responsabilidades (Endpoints, Servicios, Core, Proveedores).
*   **Patrones de Diseño (Factory):** Se implementaron `LLMFactory`, `VectorStoreFactory` (ChromaProvider), y `CheckpointerFactory` para permitir cambios fluidos entre entornos de desarrollo local (Docker) y producción (Nube/AWS) sin tocar la lógica de negocio técnica.

---

## 3. Ingesta de Datos, Chunking e Indexación Incremental

El Subsistema de Ingesta (`/api/ingest`) es responsable de poblar la base de conocimiento.

### 3.1 Ingesta Multiformato
Evolucionamos de lectores PDF crudos a un `ExtractionService` universal impulsado por **MarkItDown** de Microsoft. Esto normaliza cualquier archivo (PDF, DOCX, XLSX) a Markdown, preservando su valiosa jerarquía semántica (títulos, tablas).

### 3.2 Estrategia de Chunking Adaptativo (`ChunkingRouter`)
No todo se divide igual. El router decide basado en el archivo:
*   **Documentos Largos/Estructurados:** Utiliza `MarkdownTextSplitter` para respetar jerarquías.
*   **Textos Libres/Cortos:** Deriva al **Agentic Chunker** (Chunking Proposicional). 
    *   *Funcionamiento:* Un LLM descompone los párrafos en verdades atómicas (proposiciones sin pronombres ambiguos) y luego un Enrutador Agéntico evalúa adónde agruparlos lógicamente, creando "títulos" y "resúmenes" de cada bloque (Chunk) dinámicamente.

### 3.3 Indexación Incremental (LangChain SQLRecordManager)
Para evitar gastar tokens re-procesando documentos idénticos y limpiar duplicados, se implementó una base de datos PostgreSQL actuando como el "RecordManager":
*   Calcula y guarda un hash de cada chunk. Si rehaces una ingesta, los chunks idénticos (`num_skipped`) se ignoran, los nuevos se agregan (`num_added`), y las partes eliminadas del documento viejo son borradas de la base de datos vectorial (`num_deleted` vía `cleanup="incremental"`).

---

## 4. Agentes Inteligentes y Self-RAG (Graph)

El "cerebro" interactivo de la aplicación reside en el paquete `src/core/agent.py` y funciona sobre grafos de estados.

### 4.1 Resiliencia y Fallbacks (`AgentFactory`)
*   Se configuró **RetryPolicy** estandarizado en el `ToolNode` contra fallas de red.
*   Se usó el módulo de fallbacks nativo de LangChain: si el proveedor estrella (`gemini-1.5-pro`) colapsa, el agente migra su solicitud en un milisegundo a un modelo de rescate secundario (`gpt-4o-mini`).

### 4.2 Arquitectura Self-RAG
Abandonamos los grafos ciegos por un flujo reflexivo estricto utilizando Nodos Evaluadores (`grade_documents` y `grade_hallucinations`):
1.  **Retrieve:** Extrae contexto de ChromaDB.
2.  **Grade Documents:** Un LLM JSON verifica lógicamente si el contexto recuperado es realmente útil para responder. Si no, invoca bucles de re-intentos explícitos en el `GraphState` (`retrieve_retry_count`).
3.  **Generate:** Construye la respuesta.
4.  **Grade Hallucinations:** Un segundo evaluador compara la respuesta final con el contexto base para erradicar alucinaciones. En caso de fallos, reintenta construir (`generate_retry_count`).

**Manejo de Errores Vía Commands:** Si los validadores estructurados fallan al parsear el dictamen JSON, se captura con variables locales llamando a `Command(goto=self)`, reiniciándose hasta lograr una lectura sana y no explotar el backend.

### 4.3 Compactación de la Memoria (Summarization)
Para no saturar la ventana de tokens con charlas interminables, se creó un nodo `summarize_conversation` condicional. Si el historial supera 6 mensajes, un agente destila las conversaciones antiguas en un SystemMessage que agrupa todo lo anterior, borrando el exceso y conservando únicamente el último ida y vuelta inmodificado.

### 4.4 Checkpointer (PostgresSaver)
Tu AI no tiene pérdida de memoria tras un refresco de página. Toda iteración multi-turno está vinculada a un `thread_id` (Sesión). Su estado completo se persiste intermitentemente en tablas de PostgreSQL dedicadas de LangGraph mediante nuestro `CheckpointerFactory`.

---

## 5. Calidad, Testing y Entrega Continua (CI/CD)

### 5.1 Pruebas de Integración y Testcontainers
Apostando a estándares 2026, la carpeta `src/tests/integration/` no simula bases de datos alegremente.
*   Usa el framework **Testcontainers** para levantar Docker *on-the-fly* de ChromaDB.
*   Inyecta Mocks ("Fakes") in-house para envolver temporalmente la `LLMFactory`. Con esto logramos testear que nuestra API puede indexar y buscar vectorialmente consultando al endpoint en un test real, pero limitando llamadas aranceladas a Google y OpenAI durante el pipeline de CI.

### 5.2 GitHub Actions Workflows
*   `.github/workflows/develop.yml`: Arranca todo el entorno Docker (mapeando `/var/run/docker.sock` para Testcontainers Out-of-Docker) al crear Pull Requests hacia `develop`, pasando agresivamente Test Unitarios y de Integración.
*   `.github/workflows/main.yml`: Enfocado en producción. Configura variables ambientales (Mocks de URL de AWS/Producción), corre "Smoke Tests" Unitarios ligeros y construye formalmente el Artefacto Docker Final `docker-api` al integrar en `main`.

---

## 6. Guía Rápida de Uso (Postman)

Asegúrate de ejecutar en tu terminal local `docker compose up -d` para tener la BD Postgres, Chroma y FastAPI en pie en los puertos 8000/8001.

*   **Ingesta (POST `http://localhost:8001/api/ingest`)**
    *   Body: `form-data`. Key: `file` (Tipo File). Value: Selecciona un `.pdf` de tu PC.
*   **Consulta (POST `http://localhost:8001/api/query`) (Opciones de Agente Clásico o LangGraph via `/ask`)**
    *   Body: `raw` / `JSON`.
    *   Content: `{"message": "¿De qué trata mi documento?", "thread_id": "charla_1"}`

**(Fin Fase 1)**


C:\Python314\python.exe -m pytest src/tests
docker compose exec api pytest src/tests/unit/
