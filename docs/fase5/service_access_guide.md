# Guía de Acceso a Servicios (Personal AI Cluster)

El componente **Ingress** en nuestro clúster actúa como la "puerta de entrada" principal, enrutando todo el tráfico web a través de un único punto de acceso y distribuyéndolo a los servicios correspondientes según la ruta (el "camino" en la URL). 

Dado que no se ha especificado un `host` en las reglas del Ingress, podrás acceder a todos los servicios localmente utilizando `localhost` o la IP de tu clúster K3d.

A continuación, se detalla la URL de acceso y el propósito de cada servicio expuesto:

## 1. API Principal (FastAPI)
- **URL de Acceso:** [http://localhost/](http://localhost/)
- **Ruta Ingress:** `/`
- **Servicio Interno:** `api-service` (Puerto 80)
- **Descripción:** Es la ruta raíz del clúster. Aquí se exponen los endpoints principales de nuestra aplicación web o API (FastAPI). Por ejemplo, si tienes un endpoint de salud, podrías accederlo en `http://localhost/api/health`.

## 2. Apache Airflow (Orquestador)
- **URL de Acceso:** [http://localhost/airflow](http://localhost/airflow)
- **Ruta Ingress:** `/airflow`
- **Servicio Interno:** `airflow-webserver-svc` (Puerto 8080)
- **Descripción:** Interfaz de usuario de Airflow. Aquí puedes monitorear el estado de los DAGs (Directed Acyclic Graphs), ver los logs de los workers de Celery, y gestionar la orquestación de tareas de datos (como el Crawler de BMO).

## 3. Apache Superset (Visualización y BI)
- **URL de Acceso:** [http://localhost/superset](http://localhost/superset)
- **Ruta Ingress:** `/superset`
- **Servicio Interno:** `superset-svc` (Puerto 8088)
- **Descripción:** Plataforma de exploración de datos. Te permite conectarte a tu Lakehouse (Iceberg/Trino/Spark Thrift), ejecutar consultas SQL y crear dashboards interactivos con los datos procesados.

## 4. Spark UI (Monitoreo de Trabajos)
- **URL de Acceso:** [http://localhost/spark-ui](http://localhost/spark-ui)
- **Ruta Ingress:** `/spark-ui`
- **Servicio Interno:** `spark-thrift-svc` (Puerto 4040)
- **Descripción:** Interfaz web nativa de Apache Spark. Se utiliza para inspeccionar la ejecución de los trabajos distribuidos, revisar el uso de memoria, analizar los DAGs de ejecución física de Spark y detectar cuellos de botella en el procesamiento de datos.

---

### Notas Adicionales
* **Resolución Local:** Si por alguna razón K3d está exponiendo el balanceador de carga en un puerto diferente (por ejemplo, `8080` o `8081` en vez de `80`), tendrás que añadir ese puerto a tus URLs (ejemplo: `http://localhost:8081/airflow`).
* **Seguridad SSL:** El Ingress tiene la anotación `ingress.kubernetes.io/ssl-redirect: "false"`, lo que permite el tráfico HTTP sin cifrar (ideal para entornos de desarrollo locales).
