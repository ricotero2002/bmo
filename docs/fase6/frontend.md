¡Hola Agustin! Es un excelente paso para la evolución de tu Personal AI Knowledge Assistant. Pasar de un estado local manual a un sistema de gestión de sesiones con historial real hará que la interacción con tu sistema RAG sea mucho más robusta y natural. 

Aquí tienes un plan estructurado para implementar estas características, seguido de las pautas de optimización extraídas directamente de tu guía para que escribas código de primer nivel.

# FASE 1: Plan de Implementación (Backend)

Tu IA puede resumir el contexto para ahorrar tokens, pero la interfaz siempre debe mostrar la secuencia completa de la conversación.

1.  **Generación de Threads (Hilos):** Crea un endpoint que genere un `thread_id` único (por ejemplo, un UUID v4) cada vez que el usuario presione "Nuevo Chat". 
2.  [cite_start]**Modelado de la Base de Datos:** Tu base de datos debe almacenar no solo el texto, sino componentes granulares de los mensajes[cite: 450]. [cite_start]Necesitarás tablas para los Chats (cabecera de sesión), Mensajes (la secuencia), Partes (texto o llamadas a herramientas) y Resultados de Herramientas[cite: 452].
3.  **Endpoint de Listado:** Un `GET /api/chats?userId={id}` que devuelva la lista de conversaciones (ID del hilo, título, fecha) para poblar un panel lateral (Sidebar).
4.  **Endpoint de Historial:** Un `GET /api/chats/{threadId}/messages` que recupere todos los mensajes de un hilo específico para que el frontend los cargue al abrir una conversación antigua.
5.  [cite_start]**Persistencia en el Streaming:** Utiliza el callback `onFinish` del SDK de Vercel AI en tu backend para guardar el mensaje del usuario y la respuesta completa generada por la IA en tu base de datos sin interrumpir el streaming al cliente[cite: 454, 455].




## Phase 6 Backend Implementation: Chat History and Database
This plan outlines the steps to implement Phase 6 of the frontend/backend integration, specifically adding persistent chat history, endpoints to retrieve it, and refactoring Alembic to support both PostgreSQL and Oracle seamlessly.

Proposed Changes
Database Core & Alembic
[NEW] src/providers/database/core.py
Create a core module to encapsulate the create_engine logic currently residing inside 
status_provider.py
. This ensures it can be reused across the application and effectively solves the Alembic Postgres/Oracle duality.

[MODIFY] 
src/providers/database/status_provider.py
Update 
StatusProvider
 to import and use get_engine() from src.providers.database.core.

[MODIFY] 
alembic/env.py
Update the logic to import and use get_engine() from src.providers.database.core.

[NEW] scripts/migrate_db.sh (o 
.py
)
Crearemos un script diseñado para ejecutar alembic upgrade head sin tener que recordar los comandos ni configurar las variables de entorno manualmente. Detectará si debes correr para local (Postgres) o producción (Oracle) y aplicará los cambios directo a la rama actual.

Database Models & Provider
[MODIFY] 
src/providers/database/models.py
Add the new tables for Chats and Messages:

Chat
: 
id
 (GUID, primary_key), user_id (String), title (String), created_at (DateTime), updated_at (DateTime).
Message
: 
id
 (GUID, primary_key), chat_id (GUID, ForeignKey to chats.id), role (String: 'user' or 'assistant'), content (Text), parts (JSONText - to store tool calls or reasoning parts), created_at (DateTime).
[NEW] src/providers/database/chat_provider.py
Create ChatProvider class:

create_chat(user_id, thread_id, title)
get_user_chats(user_id)
add_message(thread_id, role, content, parts)
get_chat_messages(thread_id)
[MODIFY] 
src/api/dependencies.py
Add get_chat_provider(request: Request) to inject the ChatProvider. Initialize it in 
src/api/main.py
.

API Endpoints
[MODIFY] 
src/api/endpoints.py
Add GET /chats: Retrieves a list of conversations for a given userId (via query param). Returns a list of { thread_id, title, created_at }.
Add GET /chats/{thread_id}/messages: Retrieves all messages for a specific chat to populate the initial UI.
Update POST /ask/stream (Streaming Persistence):
In the 
event_generator()
, accumulate the full text response from the assistant.
Capture the user's initial message.
Use FastAPI's BackgroundTasks to asynchronously call ChatProvider.add_message() for both the User and the Assistant after the streaming finishes.
Verification Plan
[NEW] Automated Tests
Vamos a agregar tests específicos (con pytest y mocks o base de datos en memoria en src/tests/unit) para asegurar la solidez del sistema:

Tests para ChatProvider (test_chat_provider.py):

Validar create_chat(user_id, thread_id, title): Que cree el registro correctamente.
Validar get_user_chats(user_id): Que retorne la lista ordenada por fecha de creación descendente.
Validar add_message(thread_id, role, content, parts): Que guarde un mensaje con todos sus componentes de forma íntegra.
Validar get_chat_messages(thread_id): Que devuelva la secuencia del hilo en orden cronológico real.
Tests para la API (test_api_chats.py):

Test GET /chats: Validar que devuelva HTTP 200 y el JSON con la lista de conversaciones ({ thread_id, title, created_at }).
Test GET /chats/{thread_id}/messages: Validar HTTP 200 y que devuelva todos los mensajes del hilo. Validar HTTP 404 si el hilo no existe.
Test POST /ask/stream: Mappear una petición mock al stream y validar que la dependencia a la función background (idealmente a traves del mock de add_message) sea invocada exactamente dos veces al finalizar la respuesta (para capturar al User y al Asistente respectivamente).
Manual Verification
Use Swagger UI (http://localhost:8000/docs) to test endpoints.
Correr ./scripts/migrate_db.sh para verificar su ejecución limpia.

Ahora al mandar un mensaje a un chat sin thead crea una conversacion nueva.

# FASE 2: Plan de Implementación (Frontend)

Tengo que ver como lo voy a hacer visualmente, para que se vea bien, estaria bueno generar tipo una imagen de un asistente virtual que lo haga mas simpatico.

1.  **Contexto de Usuario (`UserContext`):** Crea un contexto usando `createContext` y `useContext`. [cite_start]Esto te permite suscribirte y leer el usuario en cualquier componente sin necesidad de pasar props manualmente a través de cada nivel del árbol de componentes (evitando el "prop drilling")[cite: 26].
2.  **Gestión del Estado Dual con TanStack Query:** Para manejar la lista de chats y el historial, implementa TanStack Query (React Query). [cite_start]Esta es la solución ideal para resolver el "Problema de Estado Dual": reconciliar el presente efímero (streaming en vivo) con el pasado persistente (base de datos)[cite: 430, 431]. [cite_start]Te permitirá cachear las consultas y evitar peticiones repetitivas al historial de chat[cite: 438].
3.  **Inyección de Historial en `useChat`:** Cuando cargues un chat existente, pásale el historial recuperado a la propiedad `initialMessages` del hook `useChat` en tu `ChatInterface.tsx`.