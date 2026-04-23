# Informe de Arquitectura de Observabilidad: Reversión de MLflow y Transición a LangSmith

## 1. Contexto y Decisión
Tras múltiples iteraciones intentando estabilizar la infraestructura de observabilidad basada en **MLflow 3.x** dentro de un entorno asíncrono (**FastAPI + LangGraph**), se ha optado por revertir completamente dicha integración y consolidar el uso de **LangSmith** como herramienta primaria de rastreo para flujos agénticos.

## 2. Problemas Identificados con MLflow
La integración de MLflow en este proyecto presentó tres conflictos técnicos críticos que comprometieron la estabilidad de la API:

1.  **Secuestro del TracerProvider (Provider Hijack)**: MLflow intenta registrar un proveedor global de OpenTelemetry. Esto entraba en conflicto directo con la instrumentación de **Grafana (OTLP)** que ya estaba configurada para métricas de salud de la API. El resultado eran errores de tipo `NoneType` al intentar serializar atributos de spans personalizados.
2.  **Conflictos de ContextVar en Asyncio**: El autologging de MLflow utiliza manejadores de contexto que, en flujos asíncronos complejos como los de LangGraph, perdían la referencia del `ContextVar` de Python. Esto generaba advertencias recurrentes de `Token was created in a different Context`, lo que eventualmente degradaba el rendimiento y la consistencia de las trazas.
3.  **Duplicidad de Spans (No-Op Spans)**: Al intentar inyectar tracers manuales para mitigar los problemas de contexto, MLflow generaba advertencias de `No Op span was created`, indicando colisiones entre el autologging global y los callbacks manuales.

## 3. Nueva Estrategia: LangSmith Selectivo
Para mantener una observabilidad premium sin los costos de complejidad y computación de MLflow, se ha implementado el siguiente esquema:

*   **Desactivación Global**: Se ha forzado `LANGCHAIN_TRACING_V2="false"` a nivel de entorno global. Esto asegura que tareas automáticas, procesos de fondo (workers de chunking) o llamadas a LLMs sueltos no consuman cuota de LangSmith ni generen ruido en el dashboard.
*   **Activación Selectiva en el Agente**: El rastreo se activa únicamente dentro de los métodos `chat` y `astream_chat` del `AgentService` utilizando el context manager `tracing_v2_enabled`.
*   **Aislamiento de Grafana**: Se ha restaurado la instrumentación pura de OpenTelemetry para FastAPI y Celery, permitiendo que Grafana siga recibiendo métricas de infraestructura sin interferencias de lógica de IA.

## 4. Cambios Realizados en la Reversión
*   **Infraestructura**: Eliminación del deployment de `mlflow-tracking-server` y sus servicios asociados en Kubernetes.
*   **Dependencias**: Eliminación de `mlflow` y dependencias pesadas de procesamiento de datos (`chromadb` en prod) para reducir el tamaño de la imagen de 1.2GB a ~600MB.
*   **Código**: Limpieza total de `main.py` y `endpoints.py`, eliminando hacks de contexto y variables de entorno de aislamiento.

## 5. Conclusión
Se prioriza la **estabilidad y simplicidad** del pipeline de producción. LangSmith ofrece una integración nativa con LangGraph que maneja correctamente la propagación de contexto asíncrono, permitiendo un debugging profundo del agente sin comprometer la disponibilidad del servicio.
