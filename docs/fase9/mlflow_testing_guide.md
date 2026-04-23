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



Ese es el verdadero desafío de poner IA en producción: en el mundo real nunca tienes un "Ground Truth" (expected output) para comparar. A este problema se le conoce en la industria como Reference-Free Evaluation (Evaluación sin referencias) o Blind Evaluation.

Para resolverlo, la industria ha adoptado el patrón de LLM-as-a-Judge (LLM como Juez). Consiste en usar un modelo muy potente (como GPT-4o, Claude 3.5 Sonnet o un Llama 3 70B) no para generar texto, sino para calificar la interacción de tu agente basándose en reglas estrictas.

Dado que en LangSmith tienes el user_input, el context (documentos recuperados) y el ai_output, puedes medir estas 3 métricas de oro que no requieren un expected output:

1. Las 3 Métricas Reference-Free para RAG
A. Fidelidad (Faithfulness / Hallucination Rate)
Qué mide: ¿El modelo se inventó datos o se apegó estrictamente a los documentos que encontró en la base vectorial?

Qué le pasas al Juez: La pregunta, el contexto recuperado y la respuesta del agente.

Cómo evalúa el Juez: Lee la respuesta y busca afirmaciones. Luego, busca si cada afirmación existe en el contexto. Si hay información en la respuesta que no está en el contexto, te pone una nota baja (Alucinación).

B. Relevancia de la Respuesta (Answer Relevance)
Qué mide: ¿El agente respondió lo que el usuario preguntó, o se fue por las ramas?

Qué le pasas al Juez: La pregunta del usuario y la respuesta del agente.

Cómo evalúa el Juez: Penaliza las respuestas evasivas o incompletas (ej. "No sé, pero te puedo hablar de otra cosa").

C. Relevancia del Contexto (Context Precision)
Qué mide: ¿Tus embeddings y Pinecone/Chroma están haciendo un buen trabajo, o están trayendo basura?

Qué le pasas al Juez: La pregunta del usuario y el contexto recuperado.

Cómo evalúa el Juez: Verifica si el texto recuperado de la base de datos realmente contiene la información necesaria para responder al usuario (independientemente de lo que haya respondido el LLM al final).

2. ¿Cómo evaluar si usó bien las Tools sin un expected?
Para evaluar el uso de herramientas (Tool Calling) sin un mapa predefinido, el Juez LLM debe actuar como un "Auditor Lógico".

Qué le pasas al Juez: El System Prompt de tu agente (donde dice qué hace cada herramienta), el mensaje del usuario y la lista de tools que el agente decidió usar (que sacas de las trazas de LangSmith).

El Prompt del Juez: "Dada esta petición del usuario y las descripciones de estas herramientas, ¿fue lógica y necesaria la secuencia de herramientas que eligió el agente? Responde YES o NO y explica por qué."

3. ¿Cómo implementar esto en tu Pipeline Nocturno?
No tienes que programar los prompts del Juez desde cero. Existen librerías estándar en la industria diseñadas exactamente para esto. Las dos mejores actualmente son DeepEval y Ragas.

Aquí tienes un ejemplo de cómo se vería tu script de evaluación en Airflow usando la librería ragas, que está hecha específicamente para evaluar sin "expected outputs":

Python
# pip install ragas pandas
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_relevancy

# 1. Transformas los datos que sacaste de LangSmith a un formato de Dataset
# (Nota: no necesitas 'expected_output')
datos_muestra = {
    "question": ["¿Qué es un Data Lakehouse?"],
    "contexts": [["Un Data Lakehouse combina la flexibilidad de un data lake con la gestión de un data warehouse..."]], # Lo que trajo tu Retriever
    "answer": ["Un Data Lakehouse es una arquitectura híbrida que une bases de datos relacionales con archivos crudos."]
}
dataset = Dataset.from_dict(datos_muestra)

# 2. Corres el LLM Juez (Por defecto usa OpenAI, pero puedes configurarle tu Llama 3.3 70b)
resultado = evaluate(
    dataset=dataset,
    metrics=[
        faithfulness,      # Mide alucinaciones (0.0 a 1.0)
        answer_relevancy,  # Mide si respondió bien (0.0 a 1.0)
    ],
)

# 3. Conviertes a DataFrame y guardas en tu MinIO / Iceberg
df_resultados = resultado.to_pandas()
print(df_resultados[['question', 'faithfulness', 'answer_relevancy']])
# df_resultados.to_parquet("s3://warehouse/gold/evaluaciones_diarias/fecha=2026-04-23/")
Resumen del Flujo de Observabilidad
Con este esquema, tu sistema LLMOps está completo:

LangSmith: Actúa como tu "caja negra", grabando absolutamente todo lo que entra, sale y pasa por el medio.

Airflow (ETL): Extrae 50 trazas al azar de LangSmith.

LLM-as-a-Judge (Ragas/DeepEval): Califica esas 50 trazas para ver si alucinó o si el Retriever falló.

Lakehouse (Iceberg): Guarda esos puntajes (0 al 1) históricos.

Grafana: Lee de Iceberg y te muestra un gráfico de líneas: "Fidelidad promedio del modelo esta semana: 92%". Si mañana haces un mal commit y cae a 70%, lo verás de inmediato.