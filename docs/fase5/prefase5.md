# Deciciones pnpm
usar pnpm


3. Cómo estructurar tus dependencias correctamente
Un error común de desarrolladores Junior es meter todo en la misma bolsa. Tu archivo package.json debe estar estrictamente estructurado:

dependencies (Producción): Aquí va SOLO lo que tu código necesita para funcionar en el servidor o en el navegador. (Ej: react, next, fastapi, axios, zod).

devDependencies (Desarrollo): Aquí va todo lo que usas para programar, compilar o testear, pero que NO se envía a producción. (Ej: typescript, eslint, jest, @types/react, tailwindcss).

Para instalarlas con pnpm: pnpm add -D tailwindcss

El Lockfile: Siempre, sin excepción, debes "commitear" tu archivo pnpm-lock.yaml (o package-lock.json) a GitHub. Este archivo garantiza que si tu compañero de trabajo (o tu servidor de producción) hace un pnpm install, descargará exactamente las mismas versiones que tú tienes, evitando el síndrome de "en mi máquina sí funciona".

Por defecto, cuando haces npm install o pnpm install, los paquetes pueden ejecutar scripts automáticos en tu computadora. Los atacantes usan esto para ejecutar malware al instante.

Solución paranoica (pero segura): Configura pnpm para ignorar scripts de terceros por defecto añadiendo ignore-scripts=true a tu archivo .npmrc.

3. Auditorías Constantes (pnpm audit)
Acostúmbrate a correr pnpm audit en tu terminal periódicamente. Esto cruza tus dependencias con bases de datos de vulnerabilidades conocidas y te avisa si alguna librería que usas tiene un hueco de seguridad crítico.

# Chat

## Fase 1: El "Senior Flex" (Contrato de Datos Tipado)
Antes de tocar un solo componente visual, debes asegurar la comunicación entre tu backend y frontend. En la ingeniería profesional, la seguridad de tipos es el pilar de la escalabilidad.

- **Generación del SDK:** Tu backend en FastAPI ya utiliza Pydantic, lo que te permite generar automáticamente especificaciones OpenAPI detalladas. Exporta el archivo `openapi.json` y utiliza herramientas como `hey-api` o `openapi-ts` para crear un SDK de TypeScript completo en tu frontend.
- **Cero Errores:** Esto crea un contrato inviolable entre FastAPI y Next.js. Si cambias un modelo Pydantic en el backend, la compilación de Next.js fallará si no actualizas las referencias, dándote un bucle de retroalimentación instantáneo.

Cuando construyes tu backend en FastAPI, utilizas clases de Pydantic para definir cómo deben verse los datos de entrada y salida. FastAPI toma estos modelos y genera automáticamente un documento llamado OpenAPI Spec (también conocido como Swagger). Este documento es un archivo openapi.json que describe absolutamente todas tus rutas, qué parámetros reciben y qué devuelven exactamente.Herramientas como @hey-api/openapi-ts leen ese archivo JSON y escriben por ti todo el código de TypeScript para el frontend.El resultado: En lugar de hacer un fetch('/api/chats') manual y cruzar los dedos para no equivocarte en el nombre de una variable, llamas a una función generada getChats() que tiene autocompletado perfecto. Si cambias algo en el backend, el frontend no compila hasta que lo arregles.

Gemini said
Esta técnica es lo que en la industria se conoce como "Tipado de Extremo a Extremo" (End-to-End Type Safety) y es una de las prácticas más valoradas en la ingeniería de software moderna.

A continuación te explico la teoría, cómo implementarlo paso a paso y cómo encaja Gemini en todo esto.

1. ¿Qué es exactamente?
Cuando construyes tu backend en FastAPI, utilizas clases de Pydantic para definir cómo deben verse los datos de entrada y salida. FastAPI toma estos modelos y genera automáticamente un documento llamado OpenAPI Spec (también conocido como Swagger). Este documento es un archivo openapi.json que describe absolutamente todas tus rutas, qué parámetros reciben y qué devuelven exactamente.
+2

Herramientas como @hey-api/openapi-ts leen ese archivo JSON y escriben por ti todo el código de TypeScript para el frontend.

El resultado: En lugar de hacer un fetch('/api/chats') manual y cruzar los dedos para no equivocarte en el nombre de una variable, llamas a una función generada getChats() que tiene autocompletado perfecto. Si cambias algo en el backend, el frontend no compila hasta que lo arregles.

2. Cómo implementarlo (Paso a Paso)
Paso A: Extraer el openapi.json de tu Backend
Asegúrate de que tu servidor FastAPI esté corriendo (por defecto en http://localhost:8000).
Puedes guardar el esquema ejecutando este comando en la terminal (desde la carpeta de tu frontend):

Bash
curl http://localhost:8000/openapi.json > openapi.json
Paso B: Instalar hey-api en Next.js
En la carpeta de tu frontend (Next.js), instala la librería de generación y el cliente base:

Bash
npm install @hey-api/client-fetch
npm install @hey-api/openapi-ts --save-dev
Paso C: Generar el SDK
Ejecuta el generador apuntando al archivo que descargaste en el Paso A. Esto creará una carpeta /src/client con todo el código tipado.

Bash
npx @hey-api/openapi-ts -i ./openapi.json -o ./src/client -c @hey-api/client-fetch
(Tip: En un entorno real, puedes poner este comando en tu package.json como un script "generate-api": "npx @hey-api...")

Paso D: Usarlo en tu código Next.js
Ahora, en lugar de usar fetch o axios a ciegas, importas los servicios generados. Mira cómo queda:

TypeScript
⚠️ La única excepción: El Streaming de Texto (Chat en vivo)El SDK generado por @hey-api es brillante para peticiones REST normales (ej: obtener el historial de chat, crear una sesión, iniciar sesión).Sin embargo, para el streaming de palabras (cuando la IA escribe letra por letra), las peticiones HTTP tradicionales no son las más adecuadas. Para el streaming, el estándar de la industria es utilizar Server-Sent Events (SSE) mediante el Vercel AI SDK (el hook useChat) en el frontend.Tu arquitectura ideal quedaría así:Para datos, historial y configuraciones: Usas el SDK autogenerado por @hey-api (100% tipado estricto).Para el chat en vivo (streaming): Usas Vercel AI SDK apuntando a un endpoint especial de tu FastAPI que devuelve un StreamingResponse.

## Fase 2: Motor de Streaming y Gestión del "Estado Dual"
En las interfaces conversacionales existe el problema del "estado dual": el estado en vivo (el mensaje que se está generando) y el estado persistente (el historial en tu base de datos PostgreSQL).

- **Estado en Vivo (Vercel AI SDK):** Olvídate de las peticiones HTTP tradicionales bloqueantes; la latencia de un LLM puede superar los 10 segundos. Implementa el Vercel AI SDK en tu frontend utilizando la función `streamText` en el servidor y el hook `useChat` en el cliente. Esto utiliza Server-Sent Events (SSE) para renderizar las palabras a medida que tu backend las transmite.
- **Estado Persistente (TanStack Query):** Para el historial de chats, utiliza TanStack Query. Al cargar la página, el servidor (Next.js) recupera los mensajes de PostgreSQL, los inyecta en la caché de React Query y los envía al cliente pre-renderizados. Esto permite que el usuario vea su historial de forma instantánea sin parpadeos visuales.

## Fase 3: Optimización de Renderizado (Componentes)
Mostrar un flujo continuo de texto (streaming) es muy exigente para el navegador. Debes estructurar tus componentes en Next.js para evitar que la interfaz se congele.

- **Mover el Estado hacia Abajo:** No pongas el estado del texto (`useState`) del input del usuario en el contenedor principal de la página. Crea un componente aislado `MessageInput` que contenga ese estado. Así, cuando el usuario escriba, solo ese pequeño componente se re-renderizará, protegiendo al pesado historial de mensajes.
- **Hijos como Propiedades (Children as Props):** Envuelve el estado de "IA pensando" en un componente contenedor y pasa tu lista de mensajes (que es pesada) como la propiedad `children`. Al hacer esto, React detecta que la referencia de `children` no cambió y se salta el re-renderizado de todo el historial de mensajes mientras la IA genera contenido, ahorrando ciclos de CPU.

## Fase 4: Diseño Profesional e Interfaz Generativa (Generative UI)
La estética y la interactividad son determinantes para la adopción de una herramienta de IA.

- **UI Minimalista:** Utiliza Tailwind CSS junto con shadcn/ui. Esta librería te permite añadir componentes directamente a tu código fuente para personalizarlos. Implementa elementos clave como el Chat Bubble para los mensajes, y el Skeleton / Shimmer como indicador de carga para mejorar visualmente la latencia percibida antes del primer token.
- **Tool Calling y Generative UI:** Como tu backend ya utiliza LangGraph y el protocolo MCP para automatización segura, puedes conectar esas llamadas a herramientas con el frontend. La Interfaz Generativa permite que el modelo devuelva componentes de React dinámicos en lugar de texto. Si el agente de tu sistema ejecuta una búsqueda o usa una herramienta, la interfaz puede renderizar un componente visual interactivo que muestre ese resultado.
# Tests De React
jest o esas cosas, ver como se hacen


# Tests Integracion

B. Testear el Chunking y Embeddings (Integration Test del RAG)
Para probar si tu Vector Database y tu estrategia de Chunking son buenas, no puedes mockear la semántica. Necesitas probar la matemática real de los vectores.

Para que esto funcione en un CI/CD sin levantar contenedores pesados, se hace lo siguiente:

Usar una Vector DB en memoria: En lugar de Redis Stack o PostgreSQL con pgvector, en tu entorno de test inicializas ChromaDB en modo efímero o FAISS. Viven en la RAM y mueren cuando termina el test.

El Golden Dataset de Retrieval: Creas un pequeño set de documentos (ej. 5 PDFs de prueba) y los ingestas en esa base de datos en memoria al inicio del test.

Métricas de DeepEval para RAG: Aquí no evalúas al agente, evalúas directamente tu función de búsqueda (tu retriever).

Usarías estas métricas específicas de DeepEval:

Contextual Precision (Precisión): ¿Los chunks más relevantes aparecieron primeros en la lista de resultados?

Contextual Recall (Exhaustividad): ¿El retriever trajo toda la información necesaria para responder, o dejó un pedazo clave afuera?

El test se vería así:

Python
from deepeval.metrics import ContextualPrecisionMetric, ContextualRecallMetric
from deepeval.test_case import LLMTestCase

## Este test no usa al agente, prueba directo tu motor de búsqueda
async def test_rag_retrieval_quality():
    # 1. Tu retriever real (conectado a Chroma/FAISS en memoria)
    retriever = get_test_vector_db() 
    
    pregunta = "¿Cuántos días de vacaciones tengo?"
    nodo_esperado = "El empleado tiene 15 días hábiles..." # Lo que DEBERÍA encontrar
    
    # 2. Ejecutar la búsqueda real (pasa por tu modelo de Embeddings real)
    documentos_recuperados = retriever.similarity_search(pregunta, k=3)
    contexto_real = [doc.page_content for doc in documentos_recuperados]

    # 3. Evaluar con DeepEval
    test_case = LLMTestCase(
        input=pregunta,
        actual_output="No importa para esta métrica",
        expected_output=nodo_esperado,
        retrieval_context=contexto_real
    )
    
    precision = ContextualPrecisionMetric(threshold=0.8)
    recall = ContextualRecallMetric(threshold=0.8)
    
    assert_test(test_case, [precision, recall])