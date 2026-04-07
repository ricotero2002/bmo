# Busqueda web

Paso 3.1: Integración de Búsqueda Web (Fallback Seguro)
DuckDuckGo es excelente porque no requiere API Keys, pero tiende a devolver mucho "ruido" (HTML residual, URLs larguísimas). Para evitar saturar la ventana de contexto del LLM, crearemos un Wrapper (Envoltorio) que limite y limpie los resultados.

1. Implementación de la Herramienta (src/tools/web_search.py):

Python
import logging
import json
from langchain_core.tools import tool
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_community.tools import DuckDuckGoSearchResults

logger = logging.getLogger(__name__)

@tool
def web_search(query: str) -> str:
    """
    Busca información en internet. ÚSALA SOLO si la base de conocimientos 
    no tiene la respuesta, o si el usuario pide explícitamente buscar en la web o noticias actuales.
    """
    logger.info(f"Ejecutando búsqueda web para: {query}")
    try:
        # Configuramos el wrapper para limitar resultados y región
        wrapper = DuckDuckGoSearchAPIWrapper(region="es-es", max_results=3)
        search = DuckDuckGoSearchResults(api_wrapper=wrapper, output_format="json")
        
        raw_results = search.invoke(query)
        
        # Limpieza y control de volumen
        try:
            results_list = json.loads(raw_results)
            cleaned_results = []
            for item in results_list:
                # Extraemos solo lo vital y limitamos el tamaño del snippet
                snippet = item.get("snippet", "")[:400] # Límite de 400 caracteres por resultado
                title = item.get("title", "Sin título")
                cleaned_results.append(f"- {title}: {snippet}...")
                
            if not cleaned_results:
                return "La búsqueda web no arrojó resultados útiles."
                
            return "Resultados de la Web:\n" + "\n".join(cleaned_results)
            
        except json.JSONDecodeError:
            # Fallback en caso de que DuckDuckGo devuelva texto plano en lugar de JSON
            return raw_results[:1500] 

    except Exception as e:
        logger.error(f"Error en web_search: {e}")
        return "Hubo un error al intentar acceder a internet."

Cosas a tener en cuenta:

Parameter Format: Region codes typically follow a [country]-[language] format, such as us-en for the United States or uk-en for the United

Esto deberia ser seteado por el agente segun el idioma que le preguntan y si le dicen un pais y sino usar el default del usuario (seria algo a agregar al crear la cuenta)

Estaria bueno chequear antes de salir de la busqueda un llm para que se fije si hay algun resultado relevante y sino no devolver nada, (aparte de chequear la alucinacion con la busqueda web en lugar de la base de conocmientos) o se puede usar el chequear relevancia que ya existe en langgraph.

# Guardar nota
Paso 3.2: Herramienta de Escritura y Persistencia
Esta herramienta es el puente entre el cerebro temporal del Agente y tu base de datos permanente. Cuando el agente la invoque, emulará lo que hace tu API recibiendo un documento.

1. Implementación de la Herramienta (src/tools/save_note.py):

python
Python
import logging
from langchain_core.tools import tool
Importa aquí tu lógica de orquestación actual
from src.orchestrator import process_new_document 

logger = logging.getLogger(__name__)

@tool
def save_note_to_knowledge_base(title: str, content: str, doc_type: str = "general") -> str:
    """
    Guarda una nueva idea, resumen o plan en la base de conocimientos permanente.
    Úsala cuando el usuario te pida guardar algo o cuando generes un resumen útil que deba ser recordado.
    """
    logger.info(f"Guardando nueva nota: {title}")
    try:
        # Formatear el contenido para que tenga sentido al ser vectorizado
        formatted_content = f"# {title}\n\n{content}"
        
        # AQUÍ: Llamas a tu orquestador existente que envía a Storage -> Celery -> Pinecone
        # process_new_document(content=formatted_content, doc_type=doc_type, source="agent_generated")
        
        return f"Nota '{title}' guardada exitosamente y enviada a la cola de vectorización."
    except Exception as e:
        logger.error(f"Error guardando nota: {e}")
        return "Hubo un error al intentar guardar la nota."

'''

# Nuevo prompt y sources
El prompt a enviar es una idea, la logica seria no borrar todo el prompt actual (como perder la parte de las fechas), pero si agregar la explicacion de los formatos, de la gerarquia de las busqudeas, que se pueden hacer ambas tipos de busquedas (para el tema de busqueads complejas) y dar un poco de ejemplos, estaria bueno que los ejemplos (few shots), no esten en el prompt sino en un archivo nuevo y se agreguen dinamicamente (para mas modularidad.)

¡Llegaste a la etapa donde la magia realmente ocurre! En esta fase, tu agente BMO deja de ser un simple buscador para convertirse en un orquestador inteligente.

Entiendo perfectamente lo que necesitas. Quieres actualizar tu System Prompt para que BMO maneje la nueva jerarquía de herramientas (base de conocimientos vs. web) de forma impecable, y además, quieres establecer un formato estandarizado para las **Citas y Fuentes** que permita a tu frontend renderizar enlaces clicleables (URLs directas a la web o Presigned URLs de tu storage para documentos locales).

Dado que estás utilizando plantillas de Jinja2, esto nos da una gran flexibilidad.

### Estrategia de Implementación

1.  **Actualización del System Prompt (`system.jinja2`):**
    * Reforzaremos la jerarquía de búsqueda (Local -> Web).
    * Añadiremos reglas estrictas sobre el formato de salida para las fuentes.
    * Incluiremos "Few-Shots" (ejemplos) directamente en el prompt para que Gemini entienda exactamente el formato esperado.
2.  **Adaptación del Backend (Storage):**
    * Para que las fuentes locales sean "clickeables", tu herramienta `knowledge_base_retriever` (en `metadata_filter.py`) necesitará generar y devolver la Presigned URL junto con el texto recuperado, de modo que BMO pueda incluirla en su respuesta final.

---

### Paso 1: El Nuevo System Prompt (`system.jinja2`)

Reemplaza el contenido actual de tu archivo `system.jinja2` con esta versión mejorada. He incorporado la lógica de la Fase 3, el formato de citas estandarizado y ejemplos claros para guiar el comportamiento de Gemini.

```jinja2
Eres un asistente experto personal y proactivo llamado BMO.
Estás hablando con {{ user_name }}.
La fecha de hoy es {{ today }} (formato ISO: YYYY-MM-DD).

Tu objetivo es contestar al usuario basándote ESTRICTAMENTE en los datos que obtienes mediante tus herramientas (tools). PROHIBIDO inventar información factual.

Tienes a tu disposición un conjunto de herramientas. Sigue estas reglas estrictamente:

# INSTRUCCIÓN CRÍTICA 1 — Jerarquía de Búsqueda (Regla de Oro)
1. PRIMERO: Busca SIEMPRE en tu `knowledge_base_retriever` (Notas personales, documentos, CV, proyectos).
2. SEGUNDO: Si la base local no tiene la respuesta, o si el usuario pregunta por eventos actuales o pide explícitamente "busca en internet", ENTONCES usa la herramienta `web_search`.
3. PROHIBIDO: NUNCA uses `web_search` para intentar buscar datos personales, notas de reuniones privadas o proyectos internos.

La herramienta `knowledge_base_retriever` acepta:
  - query (requerido).
  - date_from (opcional): Convierte expresiones de tiempo relativas ("hoy", "esta semana", "este mes") a una fecha YYYY-MM-DD concreta usando {{ today }} como referencia.
  - source_filter (opcional): Nombre exacto del archivo a filtrar.

# INSTRUCCIÓN CRÍTICA 2 — Clima
Si el usuario pregunta por el clima, DEBES invocar la herramienta correspondiente (ej: 'open_weather_map'). PROHIBIDO inventar datos meteorológicos.

# INSTRUCCIÓN CRÍTICA 3 — Memoria y Planificación
- Tienes permiso para hacer preguntas multi-salto. Ejemplo: Buscar un requerimiento localmente, luego buscar una solución técnica en la web usando esa información local, y finalmente unir ambas.
- Si generas un plan complejo, un resumen importante o el usuario te pide explícitamente "guarda esto", usa la herramienta `save_note_to_knowledge_base` para persistirlo. NO preguntes si debes guardarlo si ya te lo ordenaron.

# INSTRUCCIÓN CRÍTICA 4 — Citas y Fuentes (FORMATO OBLIGATORIO)
Siempre debes incluir citas al final de tu respuesta para que el usuario pueda verificar la información.
Tus herramientas devolverán la información junto con un enlace (URL web o Presigned URL de almacenamiento). DEBES usar un formato Markdown estándar para los enlaces, consolidándolos al final de tu respuesta bajo el título "### Fuentes".

Formato esperado:
- Para documentos locales: `[Nombre del Archivo](URL_proporcionada_por_la_herramienta)`
- Para resultados web: `[Título de la Página Web](URL_web)`

--- EJEMPLOS DE COMPORTAMIENTO Y FORMATO ---

Usuario: "¿Qué discutimos en la reunión con Siemens y qué herramientas de IA recomiendan usar ahora mismo?"
Proceso mental de BMO: 
1. Buscar localmente: knowledge_base_retriever(query="reunión Siemens") -> Devuelve notas locales y la presigned URL (ej. https://storage.com/siemens_notas.pdf?token=123).
2. Buscar en la web: web_search(query="mejores herramientas de IA actuales recomendadas para empresas") -> Devuelve resultados web con sus URLs.
Respuesta de BMO:
En la reunión con Siemens discutimos la implementación de NeMo Guardrails para asegurar la privacidad de los datos. Adicionalmente, revisando las tendencias actuales en la web, se recomienda combinar esto con frameworks como LangChain o LlamaIndex para una orquestación segura.

### Fuentes
- [notas_siemens_v2.pdf](https://storage.com/siemens_notas.pdf?token=123)
- [Mejores herramientas de IA en 2026 - TechBlog](https://www.techblog.com/ia-tools-2026)

Usuario: "Genera un resumen sobre los frameworks de IA y guárdalo en mis notas."
Proceso mental de BMO:
1. Buscar información si es necesario.
2. Generar el resumen.
3. Llamar a save_note_to_knowledge_base(title="Resumen Frameworks IA", content="...")
Respuesta de BMO:
He generado el resumen sobre los frameworks de IA y lo he guardado exitosamente en tus notas.
--------------------------------------------

Cuando hayas recibido y leído los resultados de las herramientas, TIENES que generar una respuesta redactada en lenguaje natural para el usuario. NUNCA devuelvas una respuesta vacía.
```

### Paso 2: Modificaciones Necesarias en el Backend (Para que esto funcione)

Para que el modelo pueda cumplir con la "INSTRUCCIÓN CRÍTICA 4", las herramientas deben proporcionarle las URLs.

#### A. Adaptación de `metadata_filter.py` (Base de Conocimientos)

Actualmente, tu `knowledge_base_retriever` devuelve un string formateado así:
`[Fuente: archivo.pdf | Tipo: general] ...texto...`

Debes modificarlo para que genere y devuelva la Presigned URL. La lógica exacta dependerá del servicio de storage que uses (AWS S3, MinIO, OCI Object Storage), pero conceptualmente se vería así:

```python
# Dentro de src/tools/metadata_filter.py (en la expansión de resultados)

# Importa tu fábrica o servicio de Storage
from src.providers.storage.factory import StorageFactory 

# ... (lógica de búsqueda y reranking) ...

        for doc in reranked_docs:
            source = doc.metadata.get('source', 'desconocida')
            idx = doc.metadata.get('chunk_index')
            # ... (lógica de adyacentes) ...
            
            # --- NUEVA LÓGICA DE PRESIGNED URL ---
            try:
                storage_client = StorageFactory.get_provider()
                # Generamos un enlace válido por 15 minutos, por ejemplo
                presigned_url = storage_client.generate_presigned_url(object_name=source, expiration=900)
            except Exception as e:
                logger.error(f"Error generando presigned URL para {source}: {e}")
                presigned_url = "#" # Fallback si no se puede generar
            # ---------------------------------------

            doc_type_str = doc.metadata.get('doc_type', 'general')
            # Proveemos la URL al LLM en el texto devuelto por la tool
            final_results.append(f"[Fuente: {source} | URL: {presigned_url} | Tipo: {doc_type_str}]\n{expanded_text}")

        return system_notice + "\n\n---\n\n".join(final_results)
```

#### B. Adaptación de `web_search.py` (Búsqueda Web)

Si vas a usar DuckDuckGo, asegúrate de utilizar `DuckDuckGoSearchResults` y pedirle que te devuelva el JSON, para que puedas extraer el campo `"link"` y proporcionárselo al LLM.

```python
# Dentro de src/tools/web_search.py
import json
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_community.tools import DuckDuckGoSearchResults

# ... (dentro de tu función @tool web_search) ...

        wrapper = DuckDuckGoSearchAPIWrapper(region="es-es", max_results=3)
        search = DuckDuckGoSearchResults(api_wrapper=wrapper, output_format="json")
        raw_results = search.invoke(query)
        
        try:
            results_list = json.loads(raw_results)
            cleaned_results = []
            for item in results_list:
                snippet = item.get("snippet", "")[:400]
                title = item.get("title", "Sin título")
                link = item.get("link", "#") # Extraemos el enlace
                # Proveemos la URL al LLM
                cleaned_results.append(f"- Título: {title}\n  URL: {link}\n  Contenido: {snippet}...")
                
            return "Resultados de la Web:\n" + "\n\n".join(cleaned_results)
# ...
```

### ¿Por qué esta estructura es la ideal?

* **Delegación Clara:** Al forzar la estructura `[Nombre del Archivo](URL)` en la sección "### Fuentes", el LLM formatea las URLs en Markdown estándar.
* **Facilidad para el Frontend:** Cuando tu frontend (por ejemplo, React o Vue) reciba el Markdown generado por BMO, librerías como `react-markdown` renderizarán automáticamente esos enlaces como etiquetas `<a>` clickeables. Si el enlace es una Presigned URL, al hacer clic, el navegador del usuario descargará o abrirá el PDF/imagen directamente desde tu Storage.
* **Menos alucinaciones:** Al darle ejemplos "Few-Shot" sobre cómo es su "proceso mental", Gemini entiende que está autorizado a usar la información recuperada *en combinación* con su capacidad narrativa, reduciendo errores y respuestas robóticas.

# Testing
Paso 3.4: Estrategia de Testing (Validación de Ruteo de Herramientas)
No solo necesitamos saber si el agente responde bien, sino si elige la herramienta correcta. Para esto, crearemos un test específico en Pytest que intercepte los llamados a las herramientas.

Implementación del Test (src/evals/test_tool_routing.py):

Python
import pytest
from deepeval.test_case import LLMTestCase
Asumo que tienes una función para chatear con el agente que devuelve la traza o los mensajes

@pytest.mark.asyncio
@pytest.mark.parametrize("query, expected_tool", [
    # 1. Debería usar Pinecone
    ("¿Qué discutimos en la reunión con Siemens?", "knowledge_base_retriever"),
    # 2. Debería usar Web Search (Noticia actual/Falta de datos)
    ("¿Quién ganó el premio Nobel de Física en 2025?", "web_search"),
    # 3. Debería usar Save Note
    ("Haz un resumen sobre los frameworks de IA y guárdalo en mis notas.", "save_note_to_knowledge_base")
])
async def test_agent_tool_selection(agent_service, query, expected_tool):
    """Evalúa si el agente decide usar la herramienta correcta según el contexto de la query."""
    
    # Ejecutamos el agente
    result = await agent_service.chat(message=query, thread_id="test_routing")
    messages = result.get("messages", [])
    
    # Extraemos qué herramientas intentó llamar el Agente
    called_tools = []
    for msg in messages:
        # LangChain guarda los tool calls en AIMessages
        if msg.type == "ai" and hasattr(msg, "tool_calls"):
            for tool_call in msg.tool_calls:
                called_tools.append(tool_call["name"])
                
    # Aserción: Verificamos que la herramienta esperada esté en la lista de llamadas
    assert expected_tool in called_tools, f"Fallo de enrutamiento: Para la query '{query}', se