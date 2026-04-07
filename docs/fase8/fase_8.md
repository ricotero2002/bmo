# Fase 8: Inteligencia de Grafos, Gestión de Usuarios y Madurez de Producto

Esta fase representa la evolución final de BMO, pasando de una infraestructura estable a un producto completo, inteligente y monetizable. Aquí se consolidan todas las deudas técnicas y nuevas funcionalidades identificadas durante el desarrollo de las primeras 7 fases.

---

## 🧠 1. Inteligencia Avanzada y Retrieval (Deep AI)

El objetivo es superar las limitaciones del RAG vectorial tradicional mediante relaciones y cacheo inteligente.

### 1.1 GraphRAG con Neo4j
*   **Propósito**: Resolver consultas que requieren conectar puntos entre diferentes documentos (ej: "¿Cómo se relaciona el Proyecto X de 2024 con la nota del Cliente Y de ayer?").
*   **Acción**: Integrar Neo4j para mapear entidades y relaciones extraídas mediante LLM durante la ingesta.

### 1.2 LLM Inference Cache
*   **Propósito**: Reducir costos de API y latencia en preguntas repetitivas o idénticas.
*   **Acción**: Implementar una capa de cache (Redis/DynamoDB) en `AgentService` que guarde las respuestas basadas en el hash del par (Consulta + Contexto).

### 1.3 LLM-as-a-Judge (v2)
*   **Propósito**: Automatizar la validación de calidad.
*   **Acción**: Crear una suite de regresión que compare versiones de prompts (`rag_v3` vs `rag_v4`) usando métricas de fidelidad y relevancia bajo estrés.

### 1.4 Mejorar grafo (v2)
Guardar input del usuario y output del agente y hasta 10 antes de hacer resumen (capas hacer un resumen de lo que se busco o herramientas que se usaron para dejar de contexto también)
Y solo hacer un resumen del resto con 10 o 12 mensaje y dejar el último trío ponele


---

## 👤 2. Gestión de Usuarios y Producto

Transformar la autenticación stateless en una plataforma personalizada y controlada.

### 2.1 Sincronización de Base de Datos Local
*   **Propósito**: Tener persistencia mas allá del JWT para gestionar perfiles.
*   **Acción**: Al primer login vía Auth0, crear automáticamente el registro en la tabla `users` de PostgreSQL para almacenar preferencias y metadatos.

### 2.2 Roles y Administración (RBAC)
*   **Propósito**: Habilitar funciones de control interno.
*   **Acción**: Configurar roles `admin` y `user` en Auth0. La UI debe ocultar/mostrar la "Consola de Pruebas" y logs técnicos basándose en estos permisos.

### 2.3 Sistema de Cuotas y Monetización
*   **Propósito**: Controlar el gasto operativo por usuario.
*   **Acción**: Implementar límites mensuales de mensajes (Token Buckets en Redis) y una tabla de suscripciones para gestionar límites diferenciados.

---

## 🎨 3. Experiencia de Usuario (UI/UX) y Feedback

Hacer que el sistema sea transparente y aprenda del uso real.

### 3.1 Visualización de Planificación (Reasoning Chain)
*   **Propósito**: Reducir la ansiedad del usuario durante esperas largas.
*   **Acción**: Mostrar en el frontend qué herramientas está llamando el agente y en qué paso del plan se encuentra (ej: "Buscando en notas locales...", "Escaneando la web...").

### 3.2 Human-in-the-Loop (HITL)
*   **Propósito**: Recolectar datos para el re-entrenamiento.
*   **Acción**: Endpoint `POST /api/feedback` y botones 👍/👎 en cada burbuja de chat. Si es 👎, permitir al usuario corregir la respuesta.

### 3.3 Notificaciones y Enlaces Vivos
*   **Propósito**: Mejorar la navegación.
*   **Acción**: Hacer que las fuentes citadas sean enlaces reales directos a MinIO/S3 y mostrar una barra de progreso real durante la ingesta de documentos.


### 3.4 Admin y Usuarios
Permitir tener la fase de usuarios comunes y la de admin que te deje cambiar cosas como el prompt, el nombre de usuario y cosas asi.
---

## ☁️ 4. Infraestructura y Continuidad Operativa

Asegurar la estabilidad del sistema en la nube y su despliegue real.

### 4.1 Fix de Kafka SSL (Legacy Provider)
*   **Propósito**: Estabilizar el guardado de archivos en producción.
*   **Acción**: Corregir la carga de `legacy.so` en los contenedores de producción para evitar errores de handshake con Aiven Kafka.

### 4.2 Despliegue Real (Vercel & OKE)
*   **Propósito**: Poner el sistema en internet.
*   **Acción**: Desplegar el frontend en Vercel y finalizar el despliegue del backend en Oracle Kubernetes Engine (OKE) con certificados SSL reales.

### 4.3 Observabilidad Avanzada (Grafana Cloud)
*   **Propósito**: Monitoreo de negocio.
*   **Acción**: Dashboards de distribución de modelos (cuántas veces usamos Gemini vs OpenAI) y proyección de costos basada en tokens consumidos por usuario.

---

## 🏁 Criterios de Éxito de la Fase 8
1.  **Cero Deuda**: Sin errores de SSL o librerías en logs de producción.
2.  **Multitenancy Real**: Los datos y cuotas están aislados y persistidos localmente.
3.  **Inteligencia Conectiva**: El agente responde consultas complejas usando relaciones de Neo4j.
