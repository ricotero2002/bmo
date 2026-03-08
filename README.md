├── src/
│ ├── api/ # Endpoints de FastAPI y lógica de rutas
│ ├── workers/ # Consumidores de Kafka y tareas de Celery
│ ├── core/ # Lógica compartida (Grafos de LangGraph, Prompts)
│ ├── providers/ # CAPA DE ABSTRACCIÓN (Interfaces y Clientes)
│ │ ├── vector_store/ # Implementaciones de Chroma y OpenSearch
│ │ ├── graph_store/ # Implementaciones de Neo4j (local vs Aura)
│ │ └── llm/ # Clientes para OpenAI, Mistral, Bedrock
│ ├── schemas/ # Modelos Pydantic compartidos
│ ├── tests/ # Pytest (Unitarios, Integración) DeepEval
│ ├── evals/ # DeepEval metricas 
│ └── services/ servicios utilizados en los endpoints.
├── docker/ # Dockerfiles y docker-compose.yml
├──.env.example # Plantilla de variables de entorno
├── falta git actions
└── pyproject.toml # Dependencias del proyecto
