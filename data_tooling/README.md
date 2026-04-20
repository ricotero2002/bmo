# Data Tooling Skeleton

Este arbol existe para trabajar el flujo analitico de forma separada de la API principal.

## Objetivo

- Mantener Spark, MinIO y el REST catalog en Docker Compose.
- Mantener Airflow, dbt y MLflow en un entorno local aislado.
- Usar este scaffold para simular el flujo CSV/MLflow -> Bronze -> Silver -> Gold antes de implementar la logica real.

## Setup sugerido

1. Crear un venv dedicado en la raiz del repo:

```powershell
python -m venv .venv_data
```

2. Activarlo:

```powershell
.\.venv_data\Scripts\Activate.ps1
```

3. Instalar dependencias de tooling:

```powershell
pip install -r requirements/data-local.txt
```

## Estructura

- `airflow/`: DAGs y tareas de ingesta.
- `dbt/`: proyecto dbt y modelos Bronze / Silver / Gold.

## Regla de uso

- No implementar logica en este scaffold todavia.
- Solo completar comentarios y contratos de entrada/salida cuando el flujo de prueba este definido.

## Docker

siendo que segun dice es mejor en linux, deberia hacer otro docker compose para esta parte del trabajo.
Y fijarse si no deberia usar un checkpointer o algo asi para spark para no perder info.