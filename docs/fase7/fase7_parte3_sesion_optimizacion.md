# Fase 7 — Parte 3 (Sesión de Optimización): Resumen de Cambios

**Fecha:** 2026-04-03  
**Objetivo de la sesión:** Resolver la ceguera del agente a la web, implementar Deep Search, refactorizar el ruteo post-herramienta y mejorar la robustez del auditor de tareas.

---

## 1. Cambios Implementados

### 1.1 Deep Search — `src/tools/web_search.py`

La herramienta `web_search` fue transformada de un buscador de *snippets* a un **scraper activo**.

**Antes:** DuckDuckGo devolvía 150–300 caracteres de resumen. El LLM nunca leía el artículo real.

**Después:**
- Usa `requests` + `BeautifulSoup` para descargar y parsear el HTML de las páginas.
- Extrae hasta **4000 caracteres** de texto real (solo de etiquetas `<p>`).
- Aplica scraping profundo solo a los **2 primeros resultados** para mantener latencia baja.
- Tiene *fallback* al snippet original si la página bloquea el acceso (Error 403, timeout, etc.).
- Timeout de **5 segundos** por página para no bloquear el grafo.

**Dependencias agregadas a `requirements/base.txt`:**
```
requests>=2.28.0
beautifulsoup4>=4.12.0
```

---

### 1.2 Ruteo Inteligente Post-Herramienta — `src/service/agent.py`

**Problema detectado:** Luego de ejecutar cualquier herramienta, el grafo siempre iba a `grade_documents`. Esto causaba que al ejecutar `save_note_to_knowledge_base`, el nodo evaluador intentara "calificar" un mensaje de confirmación como si fuera un documento de recuperación.

**Solución:** Nuevo método `_route_after_tools` que distingue entre:
- **Herramientas de recuperación** (`knowledge_base_retriever`, `web_search`) → van a `grade_documents` para evaluar relevancia.
- **Herramientas de acción** (`save_note_to_knowledge_base`, `get_weather`) → vuelven directamente al `agent` sin grading.

---

### 1.3 Router del Agente como Nodo — `src/service/agent.py`

**Problema detectado:** `_agent_router` era un *borde condicional* (retorna `str`). Cuando intentaba devolver un objeto `Command` para inyectar mensajes de reintento ("nudge"), LangGraph lo ignoraba silenciosamente.

**Solución:** `_agent_router` fue registrado como un **nodo del grafo** (con `workflow.add_node`) en lugar de un borde condicional. Ahora puede devolver `Command(goto=..., update=...)` para modificar el estado del grafo.

**Flujo actualizado:**
```
agent → agent_router → [tools | grade_generation_vs_documents | cleanup_rag_memory | agent (nudge)]
```

---

### 1.4 Mecanismo de "Nudge" — `src/service/agent.py`

**Problema detectado:** Cuando Gemini Flash Lite devolvía una respuesta vacía (`output_tokens: 0`) tras recuperar documentos con éxito, el grafo terminaba prematuramente con un summary vacío.

**Solución implementada:** En `_agent_router`, si el contenido es vacío pero hubo recuperación previa exitosa, se inyecta un mensaje `HumanMessage` de sistema con la instrucción explícita de sintetizar la respuesta, y se hace `goto="agent"` con `generate_retry_count += 1`.

---

### 1.5 GeminiReranker Optimizado — `src/tools/metadata_filter.py`

- Snippet por chunk aumentado de **500 a 1000 caracteres** para no perder contexto crítico.
- Prompt del reranker refactorizado para priorizar **Evidencia Directa** sobre menciones tangenciales.
- Nueva instrucción "REGLA DE ORO" que prohíbe explícitamente retornar explicaciones adicionales al array JSON.

---

### 1.6 Auditor de Tareas — `src/service/agent.py` (`_grade_task_completion`)

**Problema original:** El auditor usaba 100% LLM (Gemini Flash Lite) para detectar si el agente había completado sus tareas. El modelo hallucinated respuestas como "no se usó ninguna herramienta" incluso cuando `knowledge_base_retriever` estaba claramente en el historial.

**Solución actual (determinista primero):** La lógica fue reescrita para usar detección por palabras clave de Python **antes** de llamar al LLM:

| Caso | Condición | Acción |
|---|---|---|
| **1** | Usuario pidió guardar (`"guardar"`, `"anota"`, etc.) y `save_note_to_knowledge_base` no fue usada | ❌ Nudge al agente |
| **2** | Usuario pidió internet explícitamente (`"busca en internet"`, `"googlea"`) y `web_search` no fue usada | ❌ Nudge al agente |
| **3** | Se usó al menos una herramienta y no hay tareas críticas pendientes | ✅ OK, continuar |
| **4** | No se usó ninguna herramienta (caso extremo) | 🤖 Delegar al LLM con prompt simplificado |

---

### 1.7 Tests Corregidos

| Test | Corrección |
|---|---|
| `test_retriever_k_results` | Aserción cambiada de `>` a `>=`. El reranker puede legítimamente devolver el mismo número de docs relevantes para k=2 y k=5 si hay pocos docs relevantes en el índice. |
| `test_rag_performance[goldcase2]` | Corregido mejorando el prompt del `GeminiReranker` para que priorice evidencia directa. |
| `test_agent_rag_quality[test_data0]` | Corregido implementando el mecanismo de nudge al agente. |

---

## 2. Estado Final de Tests (última ejecución)

```
13 passed, 1 failed (en 297s)
```

**Test aún fallando:**
- `test_agent_tool_selection[save_note_to_knowledge_base]`: El agente recupera correctamente los frameworks de la KB, pero no ejecuta `save_note_to_knowledge_base` en el mismo turno. El auditor detecta la omisión pero el nudge no es suficientemente efectivo para forzar el guardado en el paso siguiente.

---

## 3. Deuda Técnica: Rediseño Completo de `_grade_task_completion`

### 3.1 El Problema Raíz

El diseño actual del auditor es **reactivo**: evalúa *después* de que el agente terminó si le faltó algo. Esto crea un loop ineficiente donde:

1. El agente responde bien la pregunta pero no guarda.
2. El auditor lo detecta y inyecta un nudge.
3. El agente está "confundido" porque ya respondió y no entiende que debe hacer una segunda acción.
4. Puede alcanzar `MAX_RETRIES` sin haber guardado, y el flujo termina de todas formas.

Los tests lo demuestran: para la query `"Qué frameworks me pidieron usar en la reunión del 15 de marzo de 2026 y guardalos en un documento"`, el agente recupera correctamente los frameworks pero no guarda.

### 3.2 Arquitectura Propuesta: Nodo de Planificación + Auditor Consciente del Plan

La idea central es separar el "decidir qué hacer" del "hacer". Se agrega un nodo de planificación **antes** del agente que crea un plan explícito, y el auditor compara lo realizado contra ese plan.

```
START
  └─ task_planner        ← NUEVO: crea el plan de acciones
       └─ agent          ← ejecuta una acción del plan
            └─ agent_router
                 ├─ tools
                 │    └─ _route_after_tools
                 │         ├─ grade_documents → grade_generation_vs_documents
                 │         └─ agent (para tools de acción)
                 └─ grade_task_completion   ← compara contra el PLAN, no solo keywords
                      ├─ agent (si falta algo del plan)
                      └─ cleanup_rag_memory (si el plan está completo)
```

#### Nodo `task_planner` (nuevo)

```python
async def _task_planner(self, state: GraphState):
    """
    Analiza la instrucción del usuario y genera un plan estructurado de acciones.
    Ejemplo de plan para "busca los frameworks y guárdalos":
    {
        "steps": [
            {"action": "search_local", "tool": "knowledge_base_retriever", "done": False},
            {"action": "save", "tool": "save_note_to_knowledge_base", "done": False}
        ]
    }
    """
    ...
    return {"task_plan": plan}
```

El `task_plan` se almacena en el `GraphState` y persiste durante toda la conversación.

#### `_grade_task_completion` consciente del plan

```python
async def _grade_task_completion(self, state: GraphState):
    task_plan = state.get("task_plan")
    used_tools = {msg.name for msg in state["messages"] if msg.type == "tool"}
    
    for step in task_plan["steps"]:
        if step["tool"] in used_tools:
            step["done"] = True
    
    pending = [s for s in task_plan["steps"] if not s["done"]]
    
    if pending:
        next_step = pending[0]
        # Si el paso pendiente es "buscar en internet" pero la búsqueda local falló
        if next_step["action"] == "search_web":
            # El agente debería haber intentado primero local → fallback a web
            ...
        return nudge_with_specific_instruction(next_step)
    
    return {"messages": []}  # Todo completado
```

#### Ventajas de este diseño

| Aspecto | Design Actual | Design Propuesto |
|---|---|---|
| **Conocimiento del plan** | Ninguno (reactivo) | Explícito desde el inicio |
| **Manejo de fallbacks** | No existe (si KB falla, se queda parado) | Puede decir "KB falló → intenta web" |
| **Multi-acción** | Frágil (keyword matching) | Determinista (tick en lista de pasos) |
| **Transparencia** | Opaca | El plan es visible en el estado del grafo |
| **Debug** | Difícil | Se puede inspeccionar `task_plan` en LangSmith |

### 3.3 Impacto en `GraphState`

```python
class GraphState(TypedDict):
    ...
    task_plan: Optional[dict]  # NUEVO: plan de acciones del nodo planificador
```

### 3.4 Casos de Uso a Cubrir

1. **Query simple** (solo recuperar): plan con 1 paso → `knowledge_base_retriever`.
2. **Query con guardado**: plan con 2 pasos → `knowledge_base_retriever` + `save_note_to_knowledge_base`.
3. **Query con búsqueda web explícita**: plan con 1 paso → `web_search`.
4. **Fallback automático**: si `knowledge_base_retriever` no devuelve nada relevante para una pregunta de conocimiento externo, el planificador puede incluir `web_search` como paso de fallback.
5. **Multi-herramienta**: buscar local → buscar web si no hay datos → guardar resumen.

---

## 4. Próximos Pasos (Fase 8)

1. **Implementar `task_planner` como nodo del grafo** con un prompt que genere un JSON de pasos.
2. **Refactorizar `_grade_task_completion`** para comparar pasos del plan contra herramientas usadas.
3. **Agregar `task_plan` a `GraphState`** y `graph_state.py`.
4. **Actualizar la suite de tests** para probar el planificador de forma aislada (unit test del planner).
5. **Re-habilitar el test `test_agent_tool_selection[save_note]`** que actualmente falla por la limitación del diseño actual.
