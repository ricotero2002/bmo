# Indexación Incremental con SQLRecordManager

Este documento explica la estrategia de indexación incremental implementada en la aplicación para optimizar la inyección de documentos (RAG).

## El Problema: Duplicados
Cuando se actualiza o reingresa un documento en una base de datos vectorial (como ChromaDB u OpenSearch) utilizando el método básico `add_documents()`, el sistema vuelve a calcular los embeddings (lo que cuesta tiempo y tokens) y guarda vectores duplicados. Esto empeora la calidad de la recuperación (retrieval) dado que el modelo tendrá varias versiones del mismo texto en sus resultados de búsqueda.

## La Solución: SQLRecordManager de LangChain
LangChain ofrece el componente `SQLRecordManager` junto con la función `index()`. Esta funcionalidad actúa como la "memoria" del proceso de ingesta:

1. **Hashing**: Por cada fragmento (*chunk*) de documento, calcula un hash basado en el contenido de texto.
2. **Registro**: Guarda este hash en una tabla SQL junto a un timestamp y el ID de origen (`source_id_key`).
3. **Comparación**: Al re-indexar, compara los nuevos hashes con los que ya están en la base de datos SQL para ese mismo origen.
4. **Sincronización Inteligente**:
   - **`num_added`**: Los fragmentos completely nuevos se insertan.
   - **`num_skipped`**: Los fragmentos que no han cambiado (mismo hash) se ignoran.
   - **`num_deleted`**: Con el modo de limpieza **`cleanup="incremental"`**, si detecta que un fragmento de una versión anterior del mismo archivo ya no existe, lo elimina de la base vectorial.

## Arquitectura de la Implementación

### 1. Entornos y PostgreSQL
El sistema está diseñado para ser consistente entre el entorno local y de producción.
- **Local (Docker)**: El archivo `docker-compose.yml` levanta un contenedor de `postgres:15` dedicado al `RecordManager`, exponiéndolo en el puerto `5432`.
- **Producción**: Se configurará a través de la variable de entorno `RECORD_MANAGER_DB_URL` para conectarse a un entorno administrado (como AWS RDS).

### 2. Factory Pattern (`RecordManagerFactory`)
Localizado en `src/providers/record_manager/factory.py`, este componente se encarga de leer la configuración del entorno, instanciar `SQLRecordManager` e inicializar sus tablas (el *schema*) automáticamente si no existen con `.create_schema()`.

### 3. Inyección de Dependencias
En `src/api/dependencies.py`, se encuentra el *callable* `get_record_manager()`, que es inyectado por FastAPI en los *endpoints* que lo requieran (como `/ingest`). Esto permite aislar y *mockear* fácilmente la base de datos para pruebas.

### 4. Capa de Servicio (`IngestionService` / `PDFService`)
Para mantener el *endpoint* de `/ingest` limpio y cumplir con el principio de responsabilidad única, la llamada a la función `index()` de LangChain se hace dentro de la capa de servicio (por ejemplo, en `PDFService.index_documents()`).

```python
from langchain.indexes import index

def index_documents(self, chunks, record_manager, vector_store):
    return index(
        docs_source=chunks,
        record_manager=record_manager,
        vector_store=vector_store,
        cleanup="incremental", # Activa la eliminación de chunks obsoletos del mismo source
        source_id_key="source" # El metadato que identifica el documento (ej. filename)
    )
```

## Pruebas (Testing)
Se han diseñado *Integration Tests* (`tests/integration/test_ingestion.py`) que mockean la base vectorial usando colecciones en memoria de ChromaDB y conectan un `RecordManager` con SQLite en memoria, simulando el proceso de subir el mismo archivo dos veces para asegurar que se retorna `num_skipped > 0` y `num_added = 0` en el reintento.
