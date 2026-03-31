# Fase 6: Frontend Ligero y Estabilización de Historial

Esta fase se centró en la creación de una interfaz visual moderna (Next.js) que permita interactuar con el asistente virtual de forma amigable, consumiendo los endpoints de la API en tiempo real (Streaming). Adicionalmente, se rehizo la lógica de persistencia del estado (Checkpointer) y se hicieron múltiples mejoras en la robustez del Agente RAG.

## 🌟 Resumen de Implementaciones

### 1. Frontend: Interfaz y Componentes (Next.js)
Se construyó el núcleo visual de la aplicación:
- **ChatInterface & Sidebar:** Creación de una interfaz principal de chat con soporte para streaming (AI SDK de Vercel) y un panel lateral para el historial de conversaciones.
- **Rutas de API en Next.js (BFF):** Se implementaron proxies locales en rutas como `/api/chat`, `/api/chats`, `/api/ingest`, `/api/delete_file` para comunicar el cliente React de forma segura con el backend de FastAPI.
- **DocumentManager & UI Global:** Nuevos componentes de interfaz para subir, listar y borrar documentos usando los nuevos endpoints.
- **Estado Global:** Integración de React Context (`UserContext`) y TanStack Query (`providers.tsx`) para la gestión sincrónica del estado en toda la app sin "prop drilling".
- *Nota: El desarrollo del frontend sienta las bases operativas, pero **la autenticación y gestión real de usuarios + sesiones** (login, JWT, permisos) queda como pendiente para futuras fases, operando temporalmente con usuarios por defecto.*

### 2. Backend: Nuevos Endpoints y Base de Datos
- **Endpoints de Chat:** Se agregaron endpoints en `endpoints.py` para listar chats (`GET /chats`), recuperar el historial de un hilo (`GET /chats/{thread_id}/messages`) y eliminar un chat por completo (`DELETE /chats/{thread_id}`).
- **Modelos de DB y Migraciones:** Se creó `chat_provider.py` para almacenar las conversaciones en la base de datos relacional. Se incorporó una nueva revisión de Alembic (`59d3d7658f0b_add_chat_history_tables_final.py`), separando la configuración central de SQLAlchemy en `core.py`.
- **Scripts de Migración:** Automatización de implementaciones y migraciones en entornos locales y remotos con el nuevo script `scripts/migrate_db.py`.

### 3. Agente: Refinamiento de Memoria y Streaming
- **Limpieza de RAG State:** Se actualizó `_summarize_conversation` en `agent.py` para purgar correctamente los documentos extraídos del historial una vez finalizada una respuesta (reteniendo únicamente el resumen y la respuesta final). Esto evitó que los metadatos arrastrados activaran innecesariamente los flujos "Anti-Alucinaciones".
- **Control de Regeneraciones UI:** Se incorporó lógica explícita en el streaming (`endpoints.py`) para notificar visualmente a la UI (`*(Borrador descartado: corrigiendo imprecisiones...)*`) cuando los verificadores de LangGraph obligan al modelo a descartar y regenerar una respuesta.

### 4. Reemplazo del Checkpointer (De Oracle a Aiven PostgreSQL)
Tras extensas pruebas documentadas, se descubrió que Oracle limitaba la persistencia de LangGraph por su tope nativo de 4000 bytes en funciones internas JSON, corrompiendo el estado en RAGs robustos. Se migró definitivamente la memoria del grafo a PostgreSQL (Aiven), asegurando estabilidad ininterrumpida sin recurrir a inyecciones de base de datos (monkey patches).

---

## 📚 Documentación Detallada Anexa (Investigaciones de la Fase)

### Oracle LangGraph Failure y Cambio de Checkpointer
Este documento detalla el análisis y los intentos de estabilizar la retención de memoria (Checkpoints) de LangGraph utilizando **Oracle Autonomous Database**, y por qué se concluyó que no es una solución viable para entornos de producción con RAG amplio, forzando la migración a **PostgreSQL (Aiven / Supabase)**.

El problema principal radicaba en que el repositorio de LangGraph Oracle subyacente guarda el estado serializándolo en JSON. Al leer el historial, ejecuta validaciones SQL nativas que en Oracle devuelven objetos `VARCHAR2(4000)`. Si la respuesta del LLM superaba ese límite, la base fallaba con `ORA-40478: output value too large`. A pesar de aplicar parches inyectando `RETURNING CLOB` o transacciones forzadas para evitar "Ghost Executions", el agregador colapsaba en el largo plazo. PostgreSQL se erigió como la solución Tier-1 para LangGraph, resolviendo todos estos dilemas nativamente con `JSONB`.

*A raíz de esto, se cambió al checkpointer aiven/postgresql y se agregó un endpoint para eliminar chats de raíz que borre simultáneamente datos de LangGraph y de las tablas de chat relacionales.*

### Frontend Planning (De prototipo a real)
Es un excelente paso para la evolución de la IA. Pasar de un estado local manual a un sistema de gestión de sesiones con historial real hace que la interacción con el sistema RAG sea mucho más robusta y natural.
El Plan de Implementación de la Fase 6 abarcó:
1. **Generación de Threads (Hilos):** IDs únicos para referenciar la charla con el checkpointer de LangGraph.
2. **Modelado de la Base de Datos:** Centralizar las abstracciones en `core.py` y correr iterativamente scripts de refactor en Alembic para `Chats` y `Messages`.
3. **Endpoints CRUD y Streaming:** Habilitar llamadas asíncronas vía BackgroundTasks para persistir silenciosamente el estado en el RDBMS sin obstruir el streaming de Event Server.
4. **Contexto NextJS Dual State:** Manejo con React Query y `useChat` de Vercel AI SDK para armonizar la carga instantánea histórica proveniente de la base de datos, con la escritura en caliente del usuario.
