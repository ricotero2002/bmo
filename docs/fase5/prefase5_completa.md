# Fase 5: Kubernetización Local, Observabilidad y Streaming (Completa)

Este documento representa la culminación de la fase de preparación para el entorno de producción, integrando la orquestación de contenedores, la telemetría avanzada y la implementación del motor de streaming para el asistente.

## 1. Hito: Kubernetización Local (k3d)
Se migró la arquitectura de una base simple en Docker Compose a un clúster de Kubernetes auto-escalable:
- **Infraestructura Híbrida:** Bases de datos en Docker, Aplicaciones en K8s via `host.k3d.internal`.
- **Escalado con KEDA:** Implementación de `ScaledObject` para Celery basado en el lag de `ingest_q`.
- **Infisical Operator:** Sincronización automática de secretos desde la nube hacia el clúster local.

## 2. Hito: Observabilidad de Nivel Profesional (OTel)
Se estableció un pipeline de telemetría distribuida conectado a **Grafana Cloud**:
- **OTel Collector:** Desplegado en el namespace `observability` para recolectar trazas y métricas.
- **Instrumentación:** FastAPI, Celery y Kafka Consumer envían datos vía gRPC (OTLP).
- **Métricas de Negocio:** Seguimiento de uso de tokens (`llm_tokens`) y documentos procesados.

## 3. Hito: Backend y Motor de Streaming
Se implementó la capacidad de respuesta en tiempo real ("word-by-word") para mejorar la experiencia de usuario:
- **FastAPI Streaming:** Uso de `StreamingResponse` para enviar fragmentos generados por el LLM.
- **Protocolo SSE:** Implementación de Server-Sent Events para mantener la conexión abierta de forma eficiente.
- **Vercel AI SDK Ready:** El backend ya cumple con el contrato de datos necesario para ser consumido por el frontend en la siguiente fase.

## 4. Troubleshooting de Kafka y Estabilización
- **Large File Ingestion:** Configuración de brokers y consumidores para manejar archivos de hasta 100MB.
- **Commit Logic:** Corrección de la lógica de offsets en el consumidor para asegurar que el lag se limpie correctamente tras un procesamiento exitoso.
- **Group Management:** Implementación de refresco de metadatos para evitar el error de `Leader epoch newer than broker epoch`.

---

## Guía de Operación Final
Para levantar todo el entorno consolidado:

```powershell
# 1. Build de imágenes
docker build --target final-api -t personal_ai_api:latest -f docker/Dockerfile .
docker build --target final-worker -t personal_ai_worker:latest -f docker/Dockerfile .

# 2. Inyección en K8s
k3d image import personal_ai_api:latest personal_ai_worker:latest -c mycluster

# 3. Aplicar Manifiestos
kubectl apply -f k8s/app-configmap.yaml
kubectl apply -f k8s/apps-deployment.yaml
kubectl apply -f k8s/keda-scaler.yaml
kubectl rollout restart deployment -n personal-ai
```

---
**Siguiente Paso:** [Fase 6: Frontend y Usuarios](docs/fases.MD#fase-6-frontend-y-usuarios)
