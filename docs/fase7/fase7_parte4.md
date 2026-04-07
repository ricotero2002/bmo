# Fase 7 Parte 4: Estabilización, Stress Test y LLMOps

## 🎯 Objetivo de la Fase
Transformar el asistente de un prototipo a un sistema robusto, medible y escalable, implementando una arquitectura de alta disponibilidad y validando su rendimiento bajo estrés extremo.

## 🛠️ Acciones Realizadas

### 1. Mejoras de Arquitectura y Estabilidad
*   **Servidor de Producción**: Migración a **Gunicorn con workers de Uvicorn** para paralelismo real.
*   **Pool de Conexiones**: Optimización de SQLAlchemy (`pool_size=20`, `max_overflow=10`) para evitar cuellos de botella en PostgreSQL.
*   **Escalado Proactivo**: Ajuste del HPA al **60% de CPU** y uso de `--prefetch-multiplier=1` en Celery para prevenir errores de memoria (OOM).
*   **Gestión de Concurrencia**: Implementación del **Semáforo Asíncrono (20)** para proteger el LLM sin rechazar conexiones.

### 2. Telemetría y Observabilidad
*   **LangSmith Tagging**: Etiquetado dinámico (`stress_test_v1`) para separar tráfico de prueba de tráfico real.
*   **Métricas de Tiempo**: Captura de **TTFT (Time To First Token)** y tiempo total de chat mediante eventos SSE en el servidor.
*   **Monitoreo de Costos**: Extracción automatizada de métricas de tokens y gastos mediante el SDK de LangSmith.

### 3. LLMOps y Calidad
*   **[ ] Human in the Loop (HITL)**: Crear la tabla `chat_feedback` y el endpoint `POST /api/feedback` para capturar la evaluación del usuario (👍/👎).
*   **[ ] Golden Dataset V2**: Automatizar la exportación de feedback positivo para alimentar la suite de evaluación.

---

## 📊 Resultados del Stress Test (30 Usuarios)

### Métricas Obtenidas
*   **Veredicto**: **Éxito Rotundo**. 0 fallos lógicos bajo carga masiva.
*   **TTFT**: 4.6s (Mediana). El sistema responde rápido a pesar del flujo RAG complejo.
*   **Latencia Promedio**: 46.3s. Estabilizada bajo carga.
*   **Costo**: $0.247 USD por el test completo (~2.33M tokens).

---

## ⚠️ Trabajo Faltante (Roadmap de Infra & Calidad)

### Infraestructura y Observabilidad
*   **[ ] Bug Crítico (Kafka SSL)**: Arreglar el error del `legacy provider` de OpenSSL en el productor de Kafka para habilitar el guardado de archivos en producción.
*   **[ ] Modelos en Grafana**: Visualizar la distribución de uso de LLMs (Gemini vs OpenAI) en los dashboards de Grafana.

### LLMOps y Calidad
*   **[ ] LLM-as-a-Judge**: Implementar evaluaciones de precisión semántica usando un modelo juez (Gemini Pro/GPT-4) para detectar alucinaciones bajo carga.

### Experiencia de Usuario (UI/UX)
*   **[ ] Visualización de Planificación**: Mostrar en el frontend qué herramientas está usando el agente y su progreso.
*   **[ ] Notificación de Ingesta**: Mostrar el ID del archivo y seguimiento de subida cuando el agente guarda un documento.
*   **[ ] Enlaces a Fuentes**: Permitir que el usuario haga clic en las fuentes citadas para ver el documento original.
