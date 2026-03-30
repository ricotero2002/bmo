# Asistente de Conocimiento Personal (Personal AI Assistant)

Un asistente personal de IA basado en la arquitectura **Self-RAG** (Retrieval-Augmented Generation) y **LangGraph**. Diseñado para procesar, indexar inteligencialmente y recuperar conocimiento a partir de tus documentos personales. Este proyecto evoluciona desde un prototipo local hacia un sistema robusto, escalable y preparado para la nube (AWS), apoyándose fuertemente en patrones de diseño como Inyección de Dependencias (Factory Pattern) para facilitar el cambio entre infraestructura local y cloud-native.

## 🚀 Estado Actual del Proyecto

Actualmente hemos **finalizado la Fase 5 (Cloud y Kubernetización)**. El sistema cuenta con una infraestructura robusta sobre Kubernetes (lista para OKE/Ampere A1), escalado inteligente **KEDA**, **Observabilidad** profesional (OpenTelemetry + Grafana Cloud) y automatización de imágenes ARM64. *Nota: El despliegue activo en el clúster cloud remoto ha quedado pospuesto como tarea pendiente.*

**Hitos alcanzados (PreFase 5):**
- **Orquestación K8s:** Despliegue de API, Workers y Consumidores en Kubernetes local.
- **Auto-escalado:** Configuración de `ScaledObjects` (KEDA) y `HPA` (CPU).
- **Observabilidad:** Pipeline de trazas y métricas con OTel Collector y Grafana Cloud.
- **Backend Streaming:** Motor de respuestas en tiempo real para el chat.

> [!TIP]
> Para el detalle técnico de la última fase, consulta [Fase 5: Kubernetización Local y Observabilidad](docs/fase5/prefase5_completa.md).

---

## 🗺️ Fases de Desarrollo

*   ✅ **Fase 1: Cimientos y RAG Inteligente Local** (¡Completada!)
*   ✅ **Fase 2: Asincronía y Escalabilidad (Workers)** (¡Completada!)
*   ✅ **Fase 3: Ingesta Robusta de Datos (Kafka & MinIO)** (¡Completada!)
*   ✅ **Fase 4: Orquestación Agéntica y Persistencia** (¡Completada!)
*   ✅ **PreFase 5: Kubernetización Local y Observabilidad** (¡Completada!)
*   ✅ **Fase 5: Despliegue en la Nube (OCI/AWS)** (¡Completada!)
    *   *Nota: Se implementó la configuración y CI/CD para despliegue remoto. El despliegue real en el clúster remoto de Kubernetes queda pendiente.*
*   ⏳ **Fase 6: Frontend Ligero** (Pendiente)
    *   Interfaz moderna básica (Next.js) y Streaming UI. (Sin sistema de gestión de usuarios completo).
*   ⏳ **Fase 7: Testing, Optimización y Análisis** (Pendiente)
    *   Optimización de parámetros del agente, pruebas anti-alucinaciones, análisis de latencias, costos (LLMs y Cloud), y rendimiento de recursos (Kubernetes local vs remoto).
*   ⏳ **Fase 8: Tareas Pendientes y Mejoras Futuras** (Pendiente)
    *   Todo lo descartado o pospuesto (ej. Despliegue remoto K8s final, Gestión de Usuarios, GraphRAG con Neo4j).

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

Acordarme los secretos de infisical, y el de ca de kafka.

kubectl create secret generic kafka-ca-cert \
  --from-file=ca.pem=./ca.pem \
  -n personal-ai
