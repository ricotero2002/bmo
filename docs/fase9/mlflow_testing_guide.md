# Guía de Pruebas: MLflow y Trazas de LangGraph

Esta guía te explicará cómo levantar el entorno modificado, generar tráfico en tu API y visualizar las trazas resultantes directamente en el dashboard de MLflow.

## 1. Aplicar la Infraestructura

Antes de probar, debemos asegurarnos de que los cambios en MinIO, Postgres y Kubernetes estén en funcionamiento.

**Paso 1: Actualizar Docker Compose**
Como agregamos el bucket `mlflow-artifacts` y expusimos el puerto de Postgres, reinicia los contenedores base:
```bash
cd docker
docker compose down
docker compose up -d
cd ..
```
> [!NOTE]
> El contenedor `minio-init` creará automáticamente el bucket de `mlflow-artifacts` al arrancar.

**Paso 2: Desplegar MLflow en K3D**
Aplica el manifiesto que creamos para levantar el servidor de MLflow dentro de tu clúster de Kubernetes:
```bash
kubectl apply -f k8s/prod/mlflow-deployment.yaml
```
Verifica que el pod esté corriendo correctamente:
```bash
kubectl get pods -n personal-ai -l app=mlflow
```

**Paso 3: Actualizar la API de FastAPI**
Dado que añadimos `mlflow` a los `requirements/base.txt` y modificamos `main.py`, debes reconstruir la imagen de tu API y redesplegarla en K3D:
```bash
# Reconstruye tu imagen de Docker (ajusta el nombre según tu configuración)
docker build -t bmo-api:latest .
# Importa la imagen a K3D
k3d image import bmo-api:latest -c <nombre-de-tu-cluster>
# Reinicia el deployment para que tome la nueva imagen
kubectl rollout restart deployment <nombre-del-deployment-api> -n bmo-agents
```

---

## 2. Acceder a la Interfaz de MLflow

MLflow está expuesto de forma permanente mediante el **Ingress** del clúster en la sub-ruta `/mlflow`.

### Paso Único: Entrar al Dashboard
Simplemente abre tu navegador en:
**[http://localhost:8081/mlflow](http://localhost:8081/mlflow)**

> [!TIP]
> Usamos el puerto **8081** porque es el puerto que K3D tiene mapeado hacia el Ingress en tu máquina Windows. Al usar `/mlflow`, no necesitas editar el archivo `hosts` ni hacer `port-forward`.

---

## 3. Generar Trazas (Testing)

Una vez en la interfaz de MLflow, notarás un experimento llamado `bmo_production_rag` a la izquierda. Si está vacío, es porque aún no hemos invocado la API.

**Ejecuta una petición a tu RAG:**
Hazle una pregunta a tu Agente a través de la API, por ejemplo usando `curl` o tu frontend/Swagger:

```bash
curl -X POST "http://localhost:<puerto-de-tu-api>/api/chat" \
     -H "Content-Type: application/json" \
     -d '{"user_message": "¿Cuál es la arquitectura de nuestro data lake?"}'
```

---

## 4. ¿Qué verás en MLflow?

Una vez que la petición a FastAPI finalice, refresca la página de **http://localhost:5000**.

1. **Experiments (Izquierda):** Haz clic en `bmo_production_rag`.
2. **Runs (Centro):** Verás una fila nueva por cada petición que le hagas a la API.
3. **Pestaña de Traces:** Al hacer clic en un "Run" y navegar a la pestaña **Traces**, verás el árbol visual de ejecución de LangGraph.

### Datos Capturados Automáticamente:
- **Árbol de Ejecución (Trace):** La cadena exacta de nodos por los que pasó LangGraph (ej. Node Retriever -> Node Tool -> LLM).
- **Latencia:** El tiempo (en ms/s) que tardó cada nodo individual y el grafo completo.
- **Tokens (Métricas):** La cantidad de `prompt_tokens`, `completion_tokens` y `total_tokens` consumidos en la llamada a la LLM.
- **Prompts Inyectados:** El texto exacto del system prompt y los mensajes enviados al modelo en ese turno.
- **Errores:** Si un nodo de LangGraph falla, verás el traceback completo capturado y la petición marcada en rojo.
