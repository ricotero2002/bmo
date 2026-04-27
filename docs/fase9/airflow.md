1. ¿Cómo funciona el nuevo Airflow con CeleryExecutor?
En tu archivo docker-compose.spark-airflow.yml, has desplegado una arquitectura distribuida clásica. Ya no hay un solo proceso haciendo todo; el trabajo se divide:

Scheduler (El Cerebro): Lee constantemente tus archivos .py en la carpeta dags/. Cuando es la hora de correr tu pipeline, el Scheduler no ejecuta la tarea. Simplemente crea un "mensaje de trabajo" y lo envía a la cola.

Redis (El Intermediario / Broker): Actúa como la sala de espera. Recibe los mensajes del Scheduler (ej. "Ejecuta la tarea de bajar datos de LangSmith") y los retiene de forma ultrarrápida en memoria.

Worker (El Músculo - Celery): Tienes un contenedor airflow-worker. Este proceso está siempre escuchando a Redis. Apenas ve que hay un trabajo en la cola, lo toma, ejecuta el script de Python o lanza el comando a Spark, y reporta el resultado. Si mañana el volumen de datos crece, puedes levantar 5 airflow-workers en paralelo y procesarán la cola 5 veces más rápido.

PostgreSQL (La Memoria): Guarda permanentemente el estado de cada tarea (Éxito, Fallo, Reintentos). Celery también lo usa como "Result Backend" para anotar que terminó su trabajo.

Esta separación te permite usar el parámetro retry_exponential_backoff=True de tu código de forma eficiente: si una tarea falla, el Worker se libera, y el Scheduler simplemente vuelve a meter la tarea en Redis 5 minutos después.


Estos dos bloques utilizan una característica avanzada de YAML llamada Anclas (Anchors) y Alias, que sirve para no repetir código. Aquí tienes exactamente qué hace cada uno dentro de tu arquitectura de Airflow:

1. airflow-common: &airflow-common (La Plantilla Base)
Este bloque no levanta ningún contenedor por sí solo. Funciona como una plantilla maestra (indicada por el símbolo &) que contiene toda la configuración estructural que necesitan los distintos componentes de Airflow para funcionar en tu clúster:

build: Define cómo construir la imagen de Docker usando tu carpeta ./airflow.

depends_on: Asegura que esta plantilla no inicie hasta que la base de datos (postgres-airflow) y el broker (redis) estén sanos.

environment: Aquí está el núcleo de la orquestación distribuida.

Activa el CeleryExecutor.

Conecta a Airflow con PostgreSQL para guardar los metadatos de las tareas (AIRFLOW__DATABASE__SQL_ALCHEMY_CONN) y para registrar los resultados de los workers de Celery (AIRFLOW__CELERY__RESULT_BACKEND).

Conecta a Airflow con Redis (AIRFLOW__CELERY__BROKER_URL) para encolar los trabajos.

Inyecta las credenciales de MinIO y las URIs del Lakehouse para que cualquier tarea de Airflow sepa a dónde mandar los datos.

volumes: Monta tus carpetas locales (dags, tasks, dbt, y tu proyecto raíz) para que Airflow detecte los cambios en tu código sin tener que reconstruir la imagen.

2. airflow-webserver: (La Interfaz Gráfica)
Este sí es un contenedor real. Es el servidor web que te muestra la interfaz gráfica de Airflow en tu navegador.

<<: *airflow-common: Aquí ocurre la magia del Alias. Esto le dice a Docker Compose: "Inyecta aquí exactamente todo lo que definí arriba en la plantilla airflow-common". Así evitas copiar y pegar todas las variables de entorno y volúmenes.

command:: Ejecuta tres pasos fundamentales antes de arrancar el servidor:

airflow db migrate: Crea o actualiza todas las tablas necesarias en PostgreSQL para que Airflow pueda registrar el estado de los DAGs.

airflow users create ...: Crea tu usuario administrador por defecto (usuario: admin, contraseña: admin). El || true al final hace que, si reinicias el contenedor y el usuario ya existe, no falle.

airflow webserver --port 8080: Finalmente, levanta el servicio de la UI en el puerto 8080 interno.

ports: - "8085:8080": Expone la interfaz en tu máquina host para que puedas entrar desde tu navegador escribiendo http://localhost:8085.

¿Por qué Redis es "suficiente" (y estándar) en Airflow?
Si estuvieras usando Celery por su cuenta para una API transaccional de un banco, te diría que corras a RabbitMQ. Pero estás usando Airflow, y Airflow tiene una red de seguridad gigante: PostgreSQL.


La Fuente de la Verdad: En Airflow, el broker (Redis) NO es la fuente de la verdad. PostgreSQL lo es. Cuando el Scheduler decide que es hora de ejecutar una tarea, anota en Postgres: "Estado: QUEUED" , y luego envía el mensaje a Redis.

El "Orphaned Task Tracker": Si Redis explota y pierde ese mensaje, el Worker de Celery nunca lo recibirá. Sin embargo, el Scheduler de Airflow tiene un proceso cíclico que revisa Postgres. Si ve que una tarea lleva demasiado tiempo en estado QUEUED sin pasar a RUNNING, asume que el mensaje se perdió en el broker, la marca como fallida y la vuelve a encolar.


Mantenimiento: Redis es extremadamente ligero y fácil de mantener en un clúster de Kubernetes. RabbitMQ consume más recursos, requiere configurar Erlang y el manejo de colas atascadas suele ser más complejo operativamente.

¿Cuándo deberías cambiar a RabbitMQ?
En tu archivo base.txt, ya tienes instalado celery[redis,pyamqp]==5.6.2 , lo que significa que tu contenedor ya tiene las librerías necesarias para usar RabbitMQ (vía pyamqp) si quisieras hacer el switch.

Te recomiendo cambiar a RabbitMQ SÓLO SI:

Vas a procesar decenas de miles de micro-tareas por minuto y la latencia del reintento automático del Scheduler de Airflow (que puede tardar un par de minutos en darse cuenta de que una tarea se perdió) es inaceptable para tu negocio.

Tienes políticas estrictas de infraestructura que prohíben brokers en memoria sin persistencia AMQP.


2026-04-07T00:00:00
2026-04-11T00:00:00


Es una excelente pregunta técnica. Para entenderlo, hay que separar quién pone la fuerza bruta (el motor) de cómo se organizan los datos (el formato).

1. El "Master Local" (local[*])
Esto define el entorno de ejecución. Cuando ponemos local[*], le estamos diciendo a Spark: "No busques un cluster de 100 servidores. Usa los núcleos de procesador que tiene este contenedor (el worker) para hacer el trabajo".

Es como si decidieras mover cajas tú mismo en lugar de contratar una flota de camiones. Es más sencillo de configurar para desarrollo local.
2. El "Spark con Iceberg"
Esto define el formato y la gestión de datos. Spark por sí solo sabe leer archivos simples (CSV, JSON, Parquet). Pero para manejar una "Tabla Iceberg" (que permite cosas como transacciones, borrar filas específicas o ver el historial de cambios), necesita librerías extra y una configuración específica.

Aunque el motor sea "local" (tú mismo moviendo las cajas), necesitas el "manual de Iceberg" para saber en qué orden poner los archivos en MinIO para que se comporten como una base de datos profesional.
En resumen:
local[*]: Es el MOTOR. Significa que el Airflow Worker hace el trabajo pesado él solo.
Iceberg: Es la INTELIGENCIA. Le dice al motor local cómo escribir en MinIO de forma que los datos queden ordenados, catalogados y con soporte para SQL avanzado.
¿Por qué lo hacemos así? Porque es la forma más barata y rápida de tener un "Data Lakehouse" profesional funcionando en tu propia computadora. Si mañana tuvieras millones de datos, solo tendrías que cambiar local[*] por la IP de un cluster real (como Amazon EMR o Databricks), y todo el resto del código seguiría funcionando igual._


. ¿Por qué usamos Spark "afuera" y "adentro" del script?
Es una cuestión de lenguaje y ejecución:

Afuera (spark-submit): Es el comando que enciende el motor. Es como girar la llave del coche. Sin esto, el sistema operativo no entendería qué hacer con un archivo que usa librerías de Spark.
Adentro (spark.read, spark.write): Es el volante y los pedales. Una vez que el motor está encendido, el script le da órdenes precisas: "Ahora lee esta carpeta", "Ahora guarda esto en Iceberg".
3. ¿Cómo maneja Spark muchísimos datos? ¿Lo divide solo?
¡Exacto! Esa es la magia de Spark. Se llama Procesamiento Distribuido:

División Automática: Cuando haces spark.read.parquet, Spark no descarga el archivo entero. Mira los metadatos y dice: "Ok, esto mide 100GB, lo voy a dividir en 1000 pedazos (Partitions) de 100MB".
Paralelismo: Como usamos local[*], si tu computadora tiene 4 núcleos, Spark procesará 4 "pedazos" a la vez. Si tuvieras un cluster de 10 servidores, procesaría cientos a la vez.
Gestión de Memoria: Spark es muy inteligente; va leyendo pedazos, los procesa y los va soltando. Nunca intenta meter todo el archivo en la RAM a menos que tú se lo pidas explícitamente (lo cual sería un error).
4. ¿Y el spark-thrift no era el motor?
Sí, es UN motor que está siempre encendido (como un taxi esperando en la parada).

DBT lo usa porque es más rápido mandarle una sola frase SQL a alguien que ya está "caliente" y encendido.
Tus scripts de Python los lanzamos con spark-submit porque suelen ser procesos más largos, pesados y complejos que necesitan su propio espacio limpio para trabajar (como un coche de alquiler que usas para un viaje largo y luego devuelves).
Resumen: Usas Spark dentro de un script de Python porque Spark es una herramienta que te permite escribir código que se "autogestiona" para no romper la memoria, dividiendo el trabajo en trozos pequeños sin que tú tengas que programar esa división a mano.

El Spark que usas dentro de register_bronze.py es el que se genera al hacer spark-submit.

Tómalo de esta manera:

spark-thrift: Es un motor "comunitario". Siempre está ahí. (Como un Autobús).
spark-submit: Es un motor "privado" que nace y muere con tu tarea. (Como un Coche de alquiler).
Actualmente, cuando Airflow ejecuta el script, alquila un "coche" (motor Spark), hace el viaje (procesa los datos) y lo devuelve (apaga el motor). El spark-thrift no se entera de nada de esto, aunque ambos usen la misma "carretera" (MinIO).

¿Cómo sería usar un Spark remoto o un Cluster?
Lo increíble de Spark es que tu script de Python (register_bronze.py) no cambiaría ni una sola línea. Lo único que cambiaría es la orden que le das a Airflow (o el comando de consola).

Si mañana tuvieras un cluster real (por ejemplo, 10 servidores conectados), solo cambiarías el parámetro --master:

Local (Hoy): spark-submit --master 'local[*]' ... (Usa la CPU de mi propia máquina)

Cluster Standalone (Remoto): spark-submit --master 'spark://192.168.1.100:7077' ... (Airflow le manda el script a un servidor central y ese servidor reparte el trabajo entre 10 máquinas)

Kubernetes: spark-submit --master 'k8s://https://mi-cluster-k8s:6443' ... (Spark levanta contenedores temporales en la nube para procesar los datos y luego los borra)

En resumen: El código de tu aplicación (el "qué hacer") es independiente de la infraestructura (el "dónde correr"). Por eso Spark es el estándar en la industria: empiezas en tu laptop con local[*] y, cuando creces, solo cambias una palabra en la configuración para escalar a petabytes de datos en la nube._