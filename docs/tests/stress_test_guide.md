# Guía de Pruebas de Estrés y Monitoreo (Fase 7)

Esta guía detalla los pasos para realizar pruebas de carga en el sistema, asegurando que el auto-escalado (KEDA/HPA) funcione correctamente y que las métricas de rendimiento se capturen en LangSmith y Locust.

## 1. Requisitos Previos

Asegúrate de tener instaladas las dependencias necesarias:
```bash
pip install locust sseclient-py
```

## 2. Preparación del Entorno

### Paso 1: Siembra de Datos (Seeding)
Antes de empezar el test, es fundamental que el sistema tenga información relevante para responder. Ejecuta el script de siembra para inyectar el **Golden Dataset**:
```bash
python seed_test_data.py
```
Este script subirá 3 documentos Markdown a nombre del usuario `locust_tester`.

### Paso 2: Detección de Estrés
El sistema ya está configurado para detectar pruebas de estrés mediante el header `X-Stress-Test: true`. Las ejecuciones con este header se etiquetarán automáticamente en LangSmith con el tag `stress_test_v1`.

## 3. Ejecución del Test de Carga

### Paso 1: Lanzar Locust
Desde la raíz del proyecto, ejecuta:
```bash
locust -f locustfile.py
```
Abre tu navegador en `http://localhost:8089`.

### Paso 2: Configuración Recomendada
*   **Number of users:** 50
*   **Spawn rate:** 5 usuarios/segundo
*   **Host:** La URL de tu API (ej: `http://localhost:8000` o la Ingress URL en K8s).

### Paso 3: Monitoreo en Tiempo Real (Kubernetes)
Abre terminales adicionales para observar cómo reacciona la infraestructura:

**Terminal - Pods:**
```bash
kubectl get pods -n personal-ai -w
```
*Deberías ver nuevos pods de `api-deployment` y `worker-deployment` creándose bajo carga.*

**Terminal - Autoscaling (HPA/KEDA):**
```bash
kubectl get hpa -n personal-ai -w
```
*Observa cómo sube el `TARGETS` (ej. lag de Kafka o uso de CPU) y aumenta el número de `REPLICAS`.*

---

## 4. Recopilación y Análisis de Métricas

### A. Rendimiento del Chat (Locust)
En la pestaña **"Statistics"** de Locust, busca las filas personalizadas:
*   **SSE TTFT:** Time To First Token (Latencia percibida por el usuario hasta que empieza a ver texto).
*   **SSE Total Chat Time:** Tiempo total desde que se envía el mensaje hasta que termina el stream.

### B. Análisis Detallado y Costos (LangSmith)
1.  Ve a tu dashboard de **LangSmith**.
2.  Aplica el filtro: `has_tag("stress_test_v1")`.
3.  **Costos:** Revisa las columnas `Tokens` y `Estimated Cost` para ver el impacto económico del test.
4.  **Latencia Pinecone:** Haz clic en una ejecución, busca el nodo `knowledge_base_retriever`. El tiempo total de ese nodo representa la latencia neta de búsqueda vectorial.

### C. Latencia de Ingesta (Viaje Completo)
Para medir cuánto tarda un documento desde que se sube hasta que está listo para ser consultado:

**Opción 1: SQL (Recomendado)**
```sql
SELECT 
    AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_ingestion_seconds,
    MAX(EXTRACT(EPOCH FROM (updated_at - created_at))) as max_ingestion_seconds
FROM ingestion_status
WHERE user_id = 'locust_tester' AND status = 'completed';
```

**Opción 2: Grafana**
Si tienes Prometheus/Grafana conectado, busca el dashboard de Celery y filtra por la métrica `celery_task_runtime_seconds` para la tarea `process_document`.

---

## 5. Mantenimiento y Limpieza (Teardown)

Para evitar que los datos de prueba ensucien el sistema y generen costos innecesarios, sigue estos pasos al finalizar tus sesiones de estrés.

### A. Limpieza de Base de Datos y Pinecone
Ejecuta el script de limpieza automatizada:
```bash
python teardown_test.py
```
Este script:
1.  Busca y elimina todos los chats del usuario `locust_tester`.
2.  Lista los documentos de `locust_tester` y encola su eliminación (limpiando SQL, Storage y Pinecone).

### B. Limpieza de LangSmith
1. Ve a tu proyecto en **LangSmith**.
2. Filtra por la etiqueta: `has_tag("stress_test_v1")`.
3. Selecciona todas las ejecuciones encontradas.
4. Haz clic en **Delete** para eliminarlas de tus métricas de uso real.

---

## 6. Criterios de Éxito
*   **TTFT P95:** Menor a 2 segundos bajo carga moderada (20 usuarios).
*   **Escalabilidad:** Los workers de Kafka deben escalar proporcionalmente al lag de mensajes.
*   **Error Rate:** Menor al 1% en peticiones HTTP 200.
