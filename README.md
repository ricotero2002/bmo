# Asistente de Conocimiento Personal (Personal AI Assistant)

Un asistente personal de IA basado en la arquitectura **Self-RAG** (Retrieval-Augmented Generation) y **LangGraph**. Diseñado para procesar, indexar inteligencialmente y recuperar conocimiento a partir de tus documentos personales. Este proyecto evoluciona desde un prototipo local hacia un sistema robusto, escalable y preparado para la nube (AWS), apoyándose fuertemente en patrones de diseño como Inyección de Dependencias (Factory Pattern) para facilitar el cambio entre infraestructura local y cloud-native.

## 🚀 Estado Actual del Proyecto

Actualmente nos encontramos finalizando la **Fase 9 (Plataforma de Datos y AI Engineering)**, consolidando el sistema como una plataforma de producción con Lakehouse, ELT automatizado y LLMOps avanzado. El sistema ha evolucionado de un agente reactivo a una infraestructura de datos robusta con trazabilidad total y evaluación automática de calidad.

**Hitos alcanzados recientemente (Fase 9):**
- **Lakehouse Iceberg + Spark Connect**: Implementación de una arquitectura de datos ACID escalable para telemetría y analítica.
- **Pipeline ELT con dbt**: Automatización de la arquitectura medallón (Bronze/Silver/Gold) para métricas de negocio y calidad.
- **LLM-as-a-Judge (DeepEval + NIM)**: Evaluación automática de fidelidad y relevancia con modelos de alta gama en NVIDIA NIM.
- **Ingesta Masiva Claim-Check**: Sincronización escalable de Notion/Obsidian con Airflow Dynamic Task Mapping y KEDA.
- **Observabilidad y BI**: Dashboards en Metabase para monitoreo de calidad/costos y Grafana para salud de infraestructura.

> [!TIP]
> Para el detalle técnico de estas optimizaciones, consulta el [Resumen Integral de Fase 9](docs/fase_9_completa.md).

---

## 🛠️ Stack Tecnológico

El proyecto utiliza un ecosistema moderno de herramientas de Datos e IA para garantizar escalabilidad y observabilidad:

- **Orquestación**: Apache Airflow 2.10.5 (CeleryExecutor)
- **Procesamiento de Datos**: Apache Spark 3.5.x (Connect & Thrift) + dbt
- **Lakehouse**: Apache Iceberg sobre Oracle Object Storage / MinIO
- **Motores de Consulta**: Trino & Spark SQL
- **IA & LLMs**: LangGraph, LangChain, DeepEval, NVIDIA NIM (Abacus, Mistral, Llama)
- **Observabilidad**: LangSmith, Prometheus, OpenTelemetry
- **Visualización & BI**: Metabase & Grafana
- **Infraestructura**: Kubernetes (OKE/K3s), Docker Compose, KEDA (Autoscaling)
- **Bases de Datos**: Aiven PostgreSQL & Oracle Autonomous Database

---

## 🗺️ Fases de Desarrollo

*   ✅ **Fase 1: Cimientos y RAG Inteligente Local** (¡Completada!)
*   ✅ **Fase 2: Asincronía y Escalabilidad (Workers)** (¡Completada!)
*   ✅ **Fase 3: Ingesta Robusta de Datos (Kafka & MinIO)** (¡Completada!)
*   ✅ **Fase 4: Orquestación Agéntica y Persistencia** (¡Completada!)
*   ✅ **PreFase 5: Kubernetización Local y Observabilidad** (¡Completada!)
*   ✅ **Fase 5: Despliegue en la Nube (OCI/AWS)** (¡Completada!)
    *   *Nota: Se implementó la configuración y CI/CD para despliegue remoto. El despliegue real en el clúster remoto de Kubernetes queda pendiente.*
*   ✅ **Fase 6: Frontend Ligero y Estabilización** (¡Completada!)
    *   Interfaz moderna básica (Next.js), Streaming UI, sistema de gestión de historiales de chat y migración de checkpointer LangGraph a PostgreSQL.
*   ✅ **Fase 7: Estabilización, Stress Test y LLMOps** (¡Completada!)
    *   Optimización de parámetros del agente, pruebas anti-alucinaciones, análisis de latencias, costos (LLMs y Cloud), y rendimiento de recursos (Kubernetes local vs remoto).
*   ✅ **Fase 8: Madurez de Producto e Inteligencia de Grafos** (¡Completada!)
    * Memoria a largo plazo optimizada, calibración total del pipeline agéntico (100% success) y optimización de concurrencia.
*   ✅ **Fase 9: Plataforma de Datos y AI Engineering** (¡Completada!)
    * Implementación de Lakehouse (Iceberg/Spark), automatización de ingesta masiva (Claim-Check), ELT con dbt y LLOps con evaluación automática.
    * Ver detalle: [Resumen Integral de Fase 9](docs/fase_9_completa.md).

---

## 📂 Estructura del Proyecto

### 📂 General

```text
├── docker/                 # Configuración de contenedores (docker-compose, Dockerfiles)
├── docs/                   # Documentación extensa (Resúmenes, decisiones y guías por fase)
│   └── fase1/              # Detalles técnicos de la Fase 1 (API, Chunking, Testcontainers)
├── postman/                # Colecciones para pruebas de endpoints
├── frontend/               # Código frontend
├── src/                    # Código fuente
│   ├── api/                # Endpoints y enrutadores de FastAPI
│   ├── core/               # Lógica de Agentes LangGraph, Prompts, GraphStates
│   ├── providers/          # Patrón Factory: Abstracciones de base de datos y LLMs
│   │   ├── checkpointer/   # Implementación PostgreSQL Saver
│   │   ├── llm/            # Clientes LLM (Gemini, Mistral, OpenAI)
│   │   ├── record_manager/ # Implementación de SQLRecordManager
│   │   └── vector_store/   # Clientes Vectoriales (Chroma, etc.)
│   ├── schemas/            # Pydantic models para Request/Responses y lógica interna
│   └── tests/              # Pruebas Unitarias e Integración (Pytest + Testcontainers)
├── .env.example            # Plantilla de configuración de entorno
├── .gitignore              # Archivos y carpetas ignoradas (/src/tests/__pycache__, etc)
├── pytest.ini              # Configuración de recolección de pruebas asíncronas
└── requirements.txt        # Dependencias principales del proyecto
```
### 📂 Frontend

```text
frontend/
├── public/                 # Imágenes, iconos, fuentes
├── app/                # 🚦 App Router: SOLO rutas, layouts y páginas
│   ├── (auth)/         # Grupos de rutas (ej. /login, /register) sin afectar la URL
│   ├── dashboard/      # Ruta /dashboard
│   ├── layout.tsx      # Layout principal
│   └── page.tsx        # Página de inicio (/)
├── components/         # 🧱 Componentes de UI reutilizables
│   ├── common/         # Botones, Inputs, Modales genéricos
│   └── layout/         # Navbar, Sidebar, Footer
├── lib/                # 🛠️ Configuraciones y utilidades de librerías
│   └── axios.ts        # Configuración de tu cliente HTTP (interceptores, tokens)
├── services/           # 🔌 Llamadas a tu API (Backend)
│   ├── auth.service.ts # Funciones de login, logout
│   └── user.service.ts # Funciones para obtener datos del usuario
├── hooks/              # 🪝 Custom React Hooks (ej. useAuth, useFetch)
├── store/              # 📦 Estado global (Zustand, Context API o Redux)
├── types/              # 🏷️ Interfaces y tipos de TypeScript compartidos
├── utils/              # 🧮 Funciones puras (formatear fechas, validaciones)
├── next.config.mjs         # Configuración de Next.js
├── package.json
└── tailwind.config.ts
```
💡 Buenas prácticas para esta estructura:
Mantén app/ ligero: Los archivos page.tsx dentro de app/ deberían dedicarse casi exclusivamente a obtener datos (Server Components) y pasárselos a componentes más pequeños. No escribas toda la UI ahí dentro.

services/ es tu puente: Centraliza todas las llamadas HTTP aquí. Si mañana cambias la ruta de tu API, solo modificas un archivo en services/ y no tienes que buscar fetch por todos tus componentes.

Usa indexación (Barrels): Dentro de tus carpetas (como components/common/), crea un archivo index.ts que exporte todo. Así podrás importar cosas de forma más limpia: import { Button, Input } from '@/components/common';.

Se inicia con npm run dev

---

## 💻 Instrucciones de Uso Rápido

### Prerrequisitos
Asegúrate de contar con Python 3.12 y tener Docker corriendo en tu sistema.

### 1. Levantar la Infraestructura Local
```bash
docker compose up -d
```
Esto levantará los contenedores necesarios, que incluyen la API (FastAPI), la base de datos PostgreSQL y la base de datos vectorial Chroma.

### 2. Entorno y Dependencias
Recomendamos el uso de un entorno virtual (idealmente con `uv` o directamente con `python -m venv`):
```bash
# Crear y activar entorno virtual
python -m venv .venv
# (En Windows)
.venv\Scripts\activate

# Instalar los requerimientos
pip install -r requirements.txt
```

Luego de esto, puedes usar las colecciones provistas en `/postman` para interactuar con los endpoints de ingesta (`/api/ingest`) y consulta (`/api/query`).

**Nota de Pruebas:** Para ejecutar los tests localmente usando Testcontainers y los mocks incorporados:
```bash
python -m pytest src/tests/
```
