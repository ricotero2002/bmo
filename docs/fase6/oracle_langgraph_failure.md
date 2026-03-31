# Por qué Oracle no funciona con LangGraph Checkpointer

Este documento detalla el análisis y los intentos de estabilizar la retención de memoria (Checkpoints) de LangGraph utilizando **Oracle Autonomous Database**, y por qué se concluyó que no es una solución viable para entornos de producción con RAG amplio, forzando la migración a **PostgreSQL (Aiven / Supabase)**.

## El Problema Inicial

LangGraph guarda un Snapshot (checkpoint) del estado completo del grafo en cada "Superstep" (transición de nodo a nodo). Cuando se usan agentes RAG, el estado incluye los mensajes recuperados de la DB (`ToolMessage`), que pueden contener varios miles de tokens de contexto.

El error principal que se presentó en los logs fue:

```
ORA-40478: output value too large (maximum: 4000)
```

## Limitación técnica de Oracle con JSON

Este error es específico de cómo interactúa el checkpointer de LangGraph (oficial o forks comunitarios) con la base de datos de Oracle:

1. El repositorio de LangGraph Oracle subyacente guarda el estado serializándolo en JSON.
2. Al leer o reconstruir el historial, se ejecutan sentencias SQL que usan funciones como `JSON_ARRAY`, `JSON_OBJECT`, y `JSON_ARRAYAGG`.
3. **Limitación:** Por defecto en Oracle, estas funciones devuelven el tipo de dato `VARCHAR2(4000)`. Si la respuesta del LLM o el contenido de los documentos recuperados de la base de datos ("ToolMessage") superan los 4000 bytes (aproximadamente 2000-3000 caracteres, dependiendo de la codificación UTF-8), Oracle lanza el error `ORA-40478` de inmediato.

## Intentos de Solución (Parches Aplicados)

Para tratar de mitigar esto, se intentó hacer una inyección a nivel objeto (Monkey Patching) sobre la librería `AsyncOracleSaver` (visto en `factory.py`).

### 1. Inyección de `RETURNING CLOB`
Se modificó dinámicamente el SQL que ejecutaba el Saver para forzar a Oracle a que devolviera un `CLOB` (Character Large Object) en lugar de un `VARCHAR2`.
```sql
JSON_ARRAY(channel, type, blob RETURNING CLOB)
```
Esto soluciona que el JSON se trunque al hacer consultas simples, pero el problema reaparecía en uniones más profundas (`JSON_ARRAYAGG`) imposibles de rastrear de manera segura solo reemplazando texto de SQL. 

### 2. Parche al Lector de Strings (Fetch Lobs)
Dado que Oracle devuelve un objeto LOB que no es un `string` nativo para Python hasta que se llama explícitamente `.read()`, el Saver explotaba al intentar deserializar. Se parchó el método `_fetch_checkpoint` y se forzó a `oracledb.defaults.fetch_lobs = False` para auto-decodificar todo.

### 3. Ghost Executions
De manera silenciosa, a veces el grafo se ejecutaba pero LangGraph no persistía el estado, perdiendo la memoria. Se descubrió que la conexión asíncrona no estaba forzando un `autocommit`, o LangGraph fallaba antes del commit y cerraba el hilo asíncrono. Se parchó con transacciones manuales.

## El Veredicto Final

A pesar de que el primer intento funcionaba correctamente bajo los parches antes descritos, fallaba estrepitosamente a la segunda o tercera petición. ¿Por qué?

1. **Retención Multi-paso:** LangGraph no solo inserta nuevos estados, sino que consolida los JSON con checkpoints pasados. Al ejecutar un "Select" o "Merge", la operación vuelve a ser obligada a pasar por el límite de 4000 caracteres de Oracle en sus agregadores. O peor, falla antes e interrumpe una lectura parcial, llevando a LangGraph a estado corrupto.
2. **Postgres al rescate:** LangGraph ofrece integración oficial de Primera Clase (Tier-1) para Postgres vía `langgraph-checkpoint-postgres`. Al ser mantenido directamente por LangChain y no sufrir de la serialización frágil a JSON en los getters/setters (Postgres tiene el tipo integrado `JSONB`), este problema es inexistente.

## Solución Global

Se decidió archivar la integración del Checkpointer con Oracle. Migrar la persistencia de chat y grafo a **Aiven PostgreSQL** con el soporte oficial, lo que elimina todo el código "sucio" (Monkery Patching) que existía en el Factory y garantiza una retención a largo plazo robusta y tolerante a los gigantes strings del RAG.
