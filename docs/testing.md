# Guía de Pruebas (Testing Guide)

Esta guía detalla cómo ejecutar las distintas pruebas del proyecto, tanto localmente como en entornos de contenedor.

## Tipos de Pruebas

1.  **Unit Tests**: Pruebas de lógica aislada (ubicadas en `src/tests/unit`).
2.  **Integration Tests**: Pruebas que requieren servicios externos (Postgres, Redis, ChromaDB). Usan `testcontainers` para levantar estos servicios automáticamente.
3.  **Agent Evaluation (DeepEval)**: Pruebas de calidad del agente LLM (ubicadas en `src/tests/agente`).

---

## 1. Pruebas Locales (Directas)

Para correr las pruebas localmente, asegúrate de tener las dependencias instaladas:
venv\Scripts\activate

```bash
pip install -r requirements/local.txt
```

### Ejecutar todas las pruebas unitarias:
```bash
pytest src/tests/unit
```

### Ejecutar pruebas de integración:
*Nota: Requiere Docker corriendo en tu máquina (para `testcontainers`).*
```bash
pytest src/tests/integration
```

### Ejecutar evaluación del agente (DeepEval):
*Nota: Requiere `OPENAI_API_KEY` o `GOOGLE_API_KEY` configurada.*
```bash
pytest src/tests/agente -v
```

---

## 2. Pruebas en Docker (Container Testing)

Si prefieres (o necesitas) probar dentro del entorno exacto de ejecución, puedes usar `docker compose exec`.

### Levantar el entorno local:
```bash
docker compose -f docker/docker-compose.yml up -d
```

### Ejecutar pruebas dentro del contenedor de la API:
```bash
docker compose -f docker/docker-compose.yml exec api pytest src/tests/unit
```

### Ejecutar pruebas específicas:
```bash
docker compose -f docker/docker-compose.yml exec api pytest src/tests/unit/test_api.py
```

---

## 3. Pruebas en CI (GitHub Actions)

Los workflows de GitHub Actions están configurados para:
- **`develop.yml`**: Ejecuta tests unitarios e integración en cada push a `develop`.
- **`main.yml`**: Ejecuta "Smoke Tests" (unitarios con config de nube) antes de considerar el build exitoso.

Asegúrate de que `requirements/local.txt` esté siempre actualizado, ya que el CI lo utiliza para instalar las herramientas de testing.
