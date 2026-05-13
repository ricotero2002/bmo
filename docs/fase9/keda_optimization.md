# Optimización y Escalado a Cero con KEDA

Este documento detalla la implementación de KEDA para el ahorro de recursos en el clúster K3s, permitiendo que Trino y Spark Connect escalen a cero réplicas cuando no están en uso.

---

## 1. Trino (Workers 0 → N)

### Lógica de Escalado
El coordinador de Trino siempre permanece encendido (~512MB RAM), pero los workers escalan según la demanda. KEDA monitorea la API de Trino cada 15 segundos.

### Configuración aplicada
1.  **Replicas Iniciales**: 0 (en `trino-values.yaml`).
2.  **Trigger**: API REST de Trino (`/v1/cluster`).
3.  **Métrica**: `runningQueries` o `queuedQueries` >= 1.
4.  **Cooldown**: 10 minutos (si no hay actividad por 10 min, los workers se apagan).

### Tolerancia a Cold Start
Para evitar que las queries fallen mientras los workers arrancan, el coordinador tiene:
*   `maxQueuedTime: "5m"`: Las consultas esperan en cola hasta 5 minutos en lugar de fallar inmediatamente.

---

## 2. Spark Connect (0 → 1)

### Lógica de Escalado
Spark Connect solo es necesario cuando Airflow está ejecutando tareas. KEDA monitorea la presencia de pods con el label `component=worker,tier=airflow`.

### Optimizaciones para Inicio Rápido
Para reducir el tiempo de arranque (Cold Start) de 2 minutos a ~15 segundos:
1.  **Imagen Custom**: `Dockerfile.spark-connect` pre-empaqueta los JARs de Iceberg y AWS en `/opt/spark/.ivy2`.
2.  **Classpath Local**: El servidor arranca usando `--conf "spark.driver.extraClassPath=/opt/spark/.ivy2/cache/*"`.
3.  **Retry en Python**: `spark_utils.py` implementa `tenacity` para reintentar la conexión gRPC durante 3 minutos con backoff exponencial.

---

## 3. Comandos de Preparación y Despliegue

### 3.1 Construir e Importar Imagen de Spark (Optimizado)
Ejecuta esto para crear la imagen con los JARs pre-cargados y meterla en tu clúster k3d:

```powershell
# Build de la imagen
docker build -t personal_ai_spark_connect:latest -f docker/spark/Dockerfile.spark-connect .

# Importar al clúster k3d (ajusta 'bmo' por el nombre de tu clúster si es distinto)
k3d image import personal_ai_spark_connect:latest -c bmo
```

### 3.2 Aplicar cambios de Infraestructura
Una vez importada la imagen, aplica las configuraciones:

```powershell
# 1. Actualizar Trino con replicas: 0
helm upgrade trino trino/trino -f k8s/lakehouse/trino-values.yaml -n personal-ai

# 2. Aplicar los ScaledObjects de KEDA y el Deployment de Spark actualizado
kubectl apply -f k8s/lakehouse/02-spark-connect.yaml
kubectl apply -f k8s/lakehouse/trino-keda.yaml
kubectl apply -f k8s/lakehouse/spark-connect-keda.yaml
```

---

## 4. Verificación
Puedes monitorear el escalado en tiempo real con:
```powershell
kubectl get scaledobject -n personal-ai -w
kubectl get pods -n personal-ai -l app=trino-worker -w
```
