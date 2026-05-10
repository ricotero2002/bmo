FROM apache/airflow:2.10.5-python3.11

USER root

# Optimización: Combinar comandos, limpiar cache y configurar Java
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jre-headless \
    procps \
    git \
    && apt-get autoremove -yqq --purge \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Configurar variables de entorno para Java (necesario para Spark/Iceberg)
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

USER airflow

# Optimización: Instalar requerimientos con cache de pip
COPY data_tooling/airflow/requirements.txt /opt/airflow/requirements.txt
RUN pip install --no-cache-dir -r /opt/airflow/requirements.txt

# Empaquetar DAGs y Tasks dentro de la imagen para que estén disponibles en K8s
COPY data_tooling/airflow/dags/ /opt/airflow/dags/
COPY data_tooling/airflow/tasks/ /opt/airflow/tasks/

# Empaquetar el src principal en /opt/project/src para que las tasks de Airflow 
# puedan importar los providers (e.g. DataLakeProvider)
COPY src/ /opt/project/src/

# DBT project para las transformaciones Silver/Gold vía Spark Thrift
COPY data_tooling/dbt/ /opt/airflow/dbt/
