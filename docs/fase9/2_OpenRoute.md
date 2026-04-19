# Fase 9.2 - Implementacion OpenRouter en LLMFactory

## Objetivo

Migrar la fabrica de modelos (`LLMFactory`) a la integracion oficial de OpenRouter, dejando como comportamiento por defecto el uso de modelos `:free`, con estrategia de fallback y metodos especialistas para LangGraph.

## Implementacion realizada

### 1. Migracion de proveedor en LLMFactory

Se reemplazo el uso previo de `ChatGoogleGenerativeAI`/`ChatOpenAI` por `ChatOpenRouter` en [src/core/llm.py](src/core/llm.py).

Cambios principales:

- Se definieron listas explicitas de modelos:
	- `HEAVY_MODEL_NAMES` (orquestacion y razonamiento complejo).
	- `LITE_MODEL_NAMES` (resumen, extraccion, clasificacion rapida).
- Se mantuvo la politica de resiliencia existente:
	- `with_fallbacks(...)` entre modelos de cada lista.
	- `with_retry(stop_after_attempt=3, wait_exponential_jitter=True)`.
- Se preservo telemetria de tokens/modelo usando callbacks via `TelemetryCallbackHandler`.
- Se forzo `include_usage` en `model_kwargs` para mantener trazabilidad de consumo.

### 2. Nuevos metodos especialistas

Se agregaron constructores especializados en [src/core/llm.py](src/core/llm.py):

- `create_planner(...)`: prioriza `liquid/lfm-2.5-1.2b-thinking:free`.
- `create_judge(...)`: prioriza modelos estrictos para evaluacion (`llama-3.3-70b` + `gemma-4-31b`).
- `create_coder(...)`: prioriza `qwen/qwen3-coder:free` para estructura/JSON.

### 3. Integracion con el flujo del agente

Se actualizo [src/service/agent.py](src/service/agent.py) para consumir los especialistas:

- `grader_docs_model` y `grader_hallucinations_model` ahora usan `create_judge(...)`.
- `task_planner_model` ahora usa `create_planner(...)`.
- `checker_completion_model` se mantiene en `create_lite(...)`.

### 4. Dependencias

Se agrego la dependencia oficial en [requirements/base.txt](requirements/base.txt):

- `langchain-openrouter`

## Testeo realizado

### Entorno

- Se creo y uso entorno virtual local: `.venv`.
- Se instalaron dependencias con:

```bash
d:/BMO/bmo/.venv/Scripts/python.exe -m pip install -r requirements/local.txt
```

### Suite de tests nueva

Se agrego [src/tests/unit/test_llm_factory_openrouter.py](src/tests/unit/test_llm_factory_openrouter.py) para validar:

1. `create()` usa la lista HEAVY y construye fallbacks.
2. `create_lite()` usa la lista LITE en orden esperado.
3. `create_planner()` prioriza el modelo thinking.
4. `create_judge()` prioriza los modelos de juez.
5. `create_coder()` prioriza `qwen/qwen3-coder:free`.

### Ejecucion

Comando ejecutado:

```bash
d:/BMO/bmo/.venv/Scripts/python.exe -m pytest src/tests/unit/test_llm_factory_openrouter.py -q
```

Resultado:

- `5 passed in 0.80s`

## Resultado de la entrega

La base OpenRouter ya esta implementada y validada por tests unitarios en entorno virtual, con default orientado a modelos `free`, fallbacks activos y especializacion por tipo de tarea del agente.
