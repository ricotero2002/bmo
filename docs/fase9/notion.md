# Notion

Notas, en la documentacion y en la baase de datos el usuario da un id como base, pero para empezar quiero obtener todas las databases de la conexion ( osea todo lo autoriazdo por el usuario) y de ahi buscar todas las paginas e ir para abajo. A la vez quiero poder identificar si una pagina fue modificada y solo bajarla cuando eso suceda. A su vez cuando una pagina sea eliminada del workspace quiero que se elimine de la base de datos. Tener en cuenta que si no exista en mi db esa pagina o contenido significa que hay que agregarlo (como si la fecha de modificacion fuera inferior.)

## Implementacion


Esto es ingeniería de sistemas complejos. Notion es un árbol (grafo) donde los nodos pueden ser páginas, bases de datos o simples bloques de texto.

Aquí tienes el plan arquitectónico completo para lograrlo, considerando las limitaciones de Notion API y tu stack (FastAPI, Airflow, MinIO, Spark, Pinecone).

Fase 1: El Modelo de Datos y el Diseño de Integración
1. ¿Qué debe proporcionar el usuario?
El usuario debe proporcionarte dos cosas:

Notion API Token: Para que tu aplicación tenga permisos de lectura.

Un ID Raíz (Root ID): El usuario debe compartir (Invite) una Página Principal o un Workspace entero con tu integración. Esa Página Principal actuará como la raíz del árbol que vas a explorar.

2. Ampliando el Modelo de Base de Datos
Tu tabla IngestionSyncState actual es muy general (rastrea la última vez que el usuario sincronizó "Notion"). Para hacer esto bien, necesitas rastrear el estado de cada bloque/página individual que descubres, porque Notion permite modificar una página secundaria sin que la página raíz cambie su last_edited_time.

Agregaremos una tabla de metadatos de sincronización a tu database/models.py:  

Python
class NotionSyncMetadata(Base):
    """
    Rastrea el estado individual de cada página/bloque descubierto en Notion.
    Permite CDC granular y detección de páginas borradas.
    """
    __tablename__ = "notion_sync_metadata"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    notion_id = Column(String(255), nullable=False, index=True) # ID de Notion (Página/Bloque)
    parent_id = Column(String(255), nullable=True) # ID del padre en Notion
    object_type = Column(String(50), nullable=False) # 'page', 'database', 'block'
    last_edited_time = Column(DateTime, nullable=True) # Extraído de la API de Notion
    file_hash = Column(String(256), nullable=True) # Hash del contenido para evitar procesar sin cambios reales
    is_archived = Column(Boolean, default=False) # Para saber si el usuario lo borró
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
Fase 2: La Estrategia de Exploración (Crawler Recursivo en Airflow)
La API de Notion no te permite descargar un "Workspace" entero con un solo botón. Tienes que arrancar en la raíz y pedirle los hijos bloque por bloque.

¿Por qué Airflow?
Airflow es perfecto para esto porque es una tarea secuencial intensiva en I/O (esperar respuestas HTTP).

El DAG ejecutará un algoritmo de Búsqueda en Anchura (BFS):

Punto de partida: Lee el source_id (ID de la página raíz) del usuario.

Cola de exploración: Mantiene una lista de IDs por revisar.

Procesamiento: Por cada ID en la cola:

Si es una Database: Usa databases.query() para obtener todas las páginas dentro de la base de datos y las añade a la cola.

Si es una Página: Pide sus metadatos (para ver last_edited_time).

Usa el endpoint avanzado /v1/pages/{page_id}/markdown (que descubriste) para obtener todo el texto limpio.

Usa /v1/blocks/{page_id}/children para buscar si hay sub-páginas o sub-bases de datos anidadas y las añade a la cola de exploración.

El Manejo de CDC y Cambios (El truco del Crawler)
Aquí es donde entra la magia del CDC sin volver a bajar 10,000 páginas:

Páginas nuevas o modificadas: Cuando el crawler llega a una página, compara el last_edited_time de la API de Notion con el que tienes guardado en NotionSyncMetadata.

Si es más nuevo, descargas el markdown, lo subes a MinIO y actualizas la base de datos.

Si el last_edited_time es el mismo, saltas la página inmediatamente (ahorrando llamadas API y ancho de banda).

Páginas borradas (Orphan detection): Después de explorar todo el árbol desde la raíz, haces un SELECT en tu tabla NotionSyncMetadata buscando las páginas de ese usuario que no visitaste en esta corrida. Si no las encontraste, significa que el usuario las movió a la papelera (in_trash=True) o les quitó los permisos. Marcas esas entradas como borradas y lanzas un evento para que Celery elimine los vectores correspondientes en Pinecone.

Fase 3: MinIO y el Disparo de Eventos
A diferencia de tu diseño anterior donde guardabas el JSON crudo de la página, ahora usarás el endpoint de Markdown Mejorado de Notion. Esto simplifica brutalmente la vida de tu Agente IA.

Airflow descarga el markdown de la página: # Proyecto X\n\n- Tarea 1...

Airflow lo sube a MinIO: s3://bronze/notion/user_1/page_123.md.

Airflow envía una petición a tu backend FastAPI informando de un nuevo archivo.

## Documentación de Notion

### 1. El Endpoint de Búsqueda Global (`search`)
**¿Para qué sirve?** 
Si el usuario simplemente te da permisos a su Workspace pero *no* te da un ID específico, o si necesitas listar todas las bases de datos a las que tienes acceso para que el usuario elija cuál sincronizar.

**¿Cuándo lo usarás?**
Al principio de tu integración (en el backend, cuando el usuario hace el setup) para listar los "Targets" posibles.

```python
from notion_client import Client

notion = Client(auth="secret_tu_token_aqui")

# Buscar todas las Bases de Datos disponibles para esta integración
response = notion.search(
    filter={
        "value": "database",
        "property": "object"
    },
    page_size=100
)

for db in response.get("results", []):
    print(f"Encontrada Base de Datos: {db['id']} - {db['title'][0]['plain_text']}")
```

---

### 2. El Endpoint de Bases de Datos (`databases.query`)
**¿Para qué sirve?**
Para listar los "hijos" (páginas o filas) que viven dentro de una tabla/base de datos de Notion. **Este es el motor principal de tu Change Data Capture (CDC).**

**¿Cuándo lo usarás?**
En Airflow, cuando la "Raíz" de la sincronización del usuario sea un Database ID. Aquí aplicas el filtro de fecha para traer solo lo modificado.

```python
def query_database_cdc(notion: Client, database_id: str, last_sync_time: str = None):
    query_payload = {}
    
    # Filtro CDC (Change Data Capture)
    if last_sync_time:
        query_payload["filter"] = {
            "timestamp": "last_edited_time",
            "last_edited_time": {
                "on_or_after": last_sync_time  # ej: "2026-04-29T10:00:00Z"
            }
        }
        
    has_more = True
    next_cursor = None
    all_pages = []
    
    while has_more:
        if next_cursor:
            query_payload["start_cursor"] = next_cursor
            
        # SINTAXIS MODERNA (notion-client >= 2.0.0)
        response = notion.databases.query(
            database_id=database_id, 
            **query_payload
        )
        
        all_pages.extend(response.get("results", []))
        has_more = response.get("has_more", False)
        next_cursor = response.get("next_cursor")
        
    return all_pages
```

---

### 3. El Endpoint de Markdown Mejorado (`pages.retrieveMarkdown`)
*(O nota importante sobre este endpoint)*
En la documentación que me pasaste, mencionan la ruta HTTP `/v1/pages/{page_id}/markdown`. Sin embargo, en el código de ejemplo oficial usan:
`notion.pages.retrieveMarkdown({ page_id: "..." })` en TypeScript.
En Python, este endpoint *aún no está integrado nativamente* en todas las versiones del cliente oficial como un método directo. Si intentas usar `notion.pages.retrieveMarkdown()` en Python y te da error, **debes usar la sesión HTTP subyacente del cliente**.

**¿Para qué sirve?**
Para descargar el texto limpio de la página sin pelear con los bloques JSON.

**¿Cuándo lo usarás?**
En Airflow, una vez que sabes qué páginas cambiaron (gracias al paso 2), descargas su contenido para mandarlo a MinIO.

```python
def get_page_markdown(notion: Client, page_id: str) -> str:
    """
    Usa el endpoint avanzado de Markdown.
    Al usar notion.request(), aprovechamos la autenticación y reintentos 
    nativos de la librería, pero apuntando a una ruta personalizada.
    """
    try:
        # Petición HTTP directa usando el cliente autenticado
        response = notion.request(
            path=f"pages/{page_id}/markdown",
            method="GET"
        )
        # El response es un dict: {"object": "page_markdown", "markdown": "...", ...}
        return response.get("markdown", "")
        
    except Exception as e:
        print(f"Error descargando markdown de {page_id}: {e}")
        return ""
```

---

### 4. El Endpoint de Bloques Hijos (`blocks.children.list`)
**¿Para qué sirve?**
Para explorar páginas anidadas. A diferencia de las Bases de Datos, una Página normal no se consulta con `query`, sino pidiendo la lista de sus "bloques hijos". 

**¿Cuándo lo usarás?**
En Airflow, si el usuario te dio como "Raíz" una Página en lugar de una Base de Datos, y necesitas saber si dentro de esa página hay links a *otras sub-páginas* (`child_page`) o *sub-bases de datos* (`child_database`). ¡Esto es clave para el Crawler Recursivo!

```python
def find_children_nodes(notion: Client, block_id: str):
    """
    Busca dentro de una página si existen sub-páginas o sub-bases de datos
    para agregarlas a la cola del Crawler.
    """
    has_more = True
    next_cursor = None
    children_nodes = []
    
    while has_more:
        # SINTAXIS OFICIAL
        response = notion.blocks.children.list(
            block_id=block_id,
            start_cursor=next_cursor,
            page_size=100
        )
        
        for block in response.get("results", []):
            # Encontramos una sub-página
            if block["type"] == "child_page":
                children_nodes.append({
                    "type": "page",
                    "id": block["id"],
                    "title": block["child_page"]["title"]
                })
            # Encontramos una sub-base de datos
            elif block["type"] == "child_database":
                children_nodes.append({
                    "type": "database",
                    "id": block["id"],
                    "title": block["child_database"]["title"]
                })
                
        has_more = response.get("has_more", False)
        next_cursor = response.get("next_cursor")
        
    return children_nodes
```

---

### 5. El Endpoint de Recuperar Nodos Individuales (`pages.retrieve` y `databases.retrieve`)
**¿Para qué sirve?**
Para obtener los metadatos exactos de un nodo (fecha de creación, fecha de última edición, si está en la papelera, etc.) sin descargar su contenido.

**¿Cuándo lo usarás?**
En el Crawler (Airflow) para verificar si un nodo ha sido modificado antes de decidir si descargar su Markdown o explorar sus hijos.

```python
def check_node_status(notion: Client, node_id: str, node_type: str):
    try:
        if node_type == "page":
            node_data = notion.pages.retrieve(page_id=node_id)
        elif node_type == "database":
            node_data = notion.databases.retrieve(database_id=node_id)
        else:
            return None
            
        return {
            "id": node_data["id"],
            "last_edited_time": node_data["last_edited_time"],
            "in_trash": node_data.get("in_trash", False),
            "url": node_data.get("url", "")
        }
    except Exception as e:
        print(f"Nodo inaccesible (quizás sin permisos o borrado permanentemente): {e}")
        return None
```

### Resumen de tu Arsenal para el Crawler

Para armar el algoritmo recursivo (BFS) en Airflow, jugarás con estas piezas como si fueran un rompecabezas:

1.  Empiezas con el ID Raíz. Usas **`check_node_status`** para saber si es página o database.
2.  Si es Database: Usas **`databases.query`** para sacar todos sus hijos.
3.  Si es Página: 
    *   Usas **`check_node_status`** para comparar el `last_edited_time` con tu DB.
    *   Si cambió, usas **`get_page_markdown`** para guardar el contenido.
    *   Usas **`blocks.children.list`** para ver si tiene `child_page` o `child_database` y agregarlos a tu cola de exploración.