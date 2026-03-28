# Roadmap de Desarrollo: Personal AI Assistant

Para llevar este proyecto de un prototipo a un sistema de grado producción, la clave es la abstracción y la escalabilidad. A continuación, se detalla el plan de ejecución actualizado:

---

# Fase 1: Cimientos y MVP Local (Completada)
- **Objetivo**: Sistema funcional básico en local.
- **Componentes**: FastAPI, ChromaDB, Gemini, PyTest.
- **Logro**: Endpoint `/ask` funcional con RAG sobre documentos locales.

# Fase 2: Asincronía y Escalabilidad (Completada)
- **Objetivo**: Separar la API del procesamiento pesado.
- **Componentes**: RabbitMQ, Celery, Redis.
- **Logro**: Ingesta asíncrona y monitoreo de tareas.

# Fase 3: Ingesta Robusta de Datos (Completada)
- **Objetivo**: Manejo de flujos de datos complejos y persistencia.
- **Componentes**: Apache Kafka, MinIO, Postgres.
- **Logro**: Ingesta via Kafka con idempotencia y almacenamiento de objetos.

# Fase 4: Orquestación Agéntica y Persistencia (Completada)
- **Objetivo**: Agente inteligente con memoria y toma de decisiones.
- **Componentes**: LangGraph, Checkpointers (Postgres/DynamoDB).
- **Logro**: Ciclo de vida agéntico, control de alucinaciones y memoria de hilos.

# PreFase 5: Kubernetización Local y Observabilidad (Completada)
- **Objetivo**: Infraestructura profesional y monitoreo en tiempo real.
- **Componentes**: k3d, KEDA, OpenTelemetry, Grafana Cloud.
- **Logro**: Auto-escalado de pods, trazabilidad distribuida y streaming de respuestas (SSE).
- **Detalle**: Ver [prefase5_completa.md](fase5/prefase5_completa.md).

# Fase 5: Despliegue Cloud-Native y Observabilidad
Migración a la nube bajo un modelo de costos optimizado.
Infraestructura: Kubernetes (EKS), Docker (Multi-stage builds).
Monitoreo:
Instrumenta FastAPI y LangGraph con OpenTelemetry para rastrear la latencia de cada "nodo" del agente.
Configura KEDA en Kubernetes para que tus workers de Celery escalen a cero si no hay tareas pendientes en Redis/RabbitMQ, ahorrando costos significativos en AWS.
Costos: Utiliza instancias Spot para los workers de procesamiento y Amazon Bedrock (vía LangChain) para cambiar entre modelos (ej. de Claude a Llama-3) según la complejidad de la tarea y el presupuesto.

# Fase 6: Frontend, Usuarios y Seguridad (En Progreso)
- **Objetivo**: Interfaz visual moderna y gestión multitenant.
- **Componentes**: Next.js (TypeScript), Tailwind CSS, shadcn/ui, Vercel AI SDK.
- **Hitos**: 
  - Chat streaming interactivo.
  - Autenticación y aislamiento de datos por usuario.
  - Implementación de límites de tasa (Rate Limiting).

# Fase 7: GraphRAG y Grafos de Conocimiento (Pendiente)
- **Objetivo**: Relaciones complejas y base de datos de grafos.
- **Componentes**: Neo4j.
- **Hitos**: Descubrimiento de relaciones entre entidades y búsqueda multidimensional.

---
*Este roadmap refleja la evolución técnica del proyecto hacia una arquitectura Cloud-Native.*

kubectl apply -f k8s/prod/
kubectl rollout restart deployment -n personal-ai
