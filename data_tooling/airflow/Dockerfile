FROM apache/airflow:2.10.5-python3.11

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --- Cambiamos a airflow para instalar paquetes de Python ---
USER airflow
COPY data_tooling/airflow/requirements.txt /opt/airflow/requirements.txt
RUN pip install --no-cache-dir -r /opt/airflow/requirements.txt

# --- Cambiamos a root para copiar archivos y setear permisos de dbt ---
USER root
COPY --chown=airflow:root data_tooling/airflow/dags/ /opt/airflow/dags/
COPY --chown=airflow:root data_tooling/airflow/tasks/ /opt/airflow/tasks/
COPY --chown=airflow:root src/ /opt/project/src/
COPY --chown=airflow:root data_tooling/dbt/ /opt/airflow/dbt/

RUN mkdir -p /opt/airflow/dbt/logs /opt/airflow/dbt/target \
    && chown -R airflow:root /opt/airflow/dbt \
    && chmod -R 775 /opt/airflow/dbt

# --- Volvemos a airflow para la ejecución ---
USER airflow
WORKDIR /opt/airflow
