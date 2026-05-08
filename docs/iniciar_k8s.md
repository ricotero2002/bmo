🚀 Protocolo Fénix: Recreación Total del Clúster BMO
Este documento asume que estás en la raíz de tu proyecto (D:\BMO\bmo) usando PowerShell.

Fase 0: Purgar la Corrupción (Hard Reset)
Vamos a matar el subsistema de Linux y limpiar la basura de Docker para asegurarnos de que la red fantasma desaparezca para siempre.

Cierra la aplicación Docker Desktop por completo (Click derecho en el ícono de la barra de tareas -> Quit).

Abre tu PowerShell como Administrador y ejecuta:

PowerShell
# Apagar WSL a la fuerza
wsl --shutdown
Vuelve a abrir Docker Desktop y espera a que el ícono esté en verde.

Limpia el clúster viejo y redes huérfanas:

PowerShell
k3d cluster delete mycluster
docker network prune -f

Fase 2: Nacimiento del Nuevo Clúster
Creamos el clúster mapeando el puerto 8081 para que el Ingress de Traefik pueda enrutar el tráfico a tu API y a Airflow.

PowerShell
k3d cluster create mycluster --api-port 6443 -p "8081:80@loadbalancer"

# Aseguramos que kubectl esté apuntando al clúster nuevo
k3d kubeconfig merge mycluster -d -s

kubectl config set-cluster k3d-mycluster --server=https://127.0.0.1:6443

Fase 3: Operadores del Sistema (KEDA e Infisical)
Kubernetes necesita aprender qué es un ScaledObject y un InfisicalSecret antes de que intentes desplegar tus apps.

PowerShell
# 1. Instalar KEDA (Autoescalado)
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm upgrade --install keda kedacore/keda --namespace keda --create-namespace

# 2. Instalar Infisical Operator (Manejo de Secretos)
helm repo add infisical https://dl.cloudsmith.io/public/infisical/helm-charts/helm/charts/
helm repo update
helm upgrade --install infisical-operator infisical/secrets-operator --namespace infisical-operator-system --create-namespace
Fase 4: Preparación del Entorno y Secretos Manuales
Creamos el barrio de tu app y le inyectamos los certificados y llaves maestras.

PowerShell
# 1. Crear el namespace principal
kubectl create namespace personal-ai
kubectl create namespace observability


# 3. Inyectar la llave maestra de Infisical (Reemplaza con tus valores reales)
kubectl create secret generic infisical-auth-secret `
  --from-literal=clientId="TU_CLIENT_ID" `
  --from-literal=clientSecret="TU_CLIENT_SECRET" `
  --namespace personal-ai

kubectl create secret generic app-secrets `
  --from-literal=GRAFANA_USERNAME="<TU_INSTANCE_ID>" `
  --from-literal=GRAFANA_TOKEN="<TU_TOKEN_DE_GRAFANA_CLOUD>" `
  --namespace observability

# 3.5. Inyectar el certificado de Kafka (Necesario para API y Worker)
kubectl create secret generic kafka-ca-cert --from-file=ca.pem=ca.pem --namespace personal-ai

# 4. Sincronizar todos los secretos de la app
# (Esto lee de Infisical y crea el secret 'app-secrets')
kubectl apply -f k8s/prod/infisical-config.yaml

# 5. Aplicar el yamls
kubectl apply -f k8s/prod/
kubectl apply -f k8s/lakehouse/



### Fase 4: OpenTelemetry (¡Soluciona el Error 2!)
Usamos Helm para desplegar el colector, pasándole tu archivo de valores.

```powershell
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update

# Aquí es donde usamos el archivo .yaml correctamente:
helm upgrade --install otel-collector open-telemetry/opentelemetry-collector `
  --namespace observability `
  -f k8s/prod/otel-collector-values.yaml
```

Fase 5: Compilación e Inyección de Imágenes
Vamos a hornear el código actualizado (incluyendo los arreglos del Juez y los timeouts de NVIDIA) y lo pasaremos al clúster.

PowerShell
# 1. Construir imágenes
docker build --target final-api -t personal_ai_api:latest -f docker/Dockerfile .
docker build --target final-worker -t personal_ai_worker:latest -f docker/Dockerfile .
docker build -t personal_ai_airflow:latest -f data_tooling/airflow/Dockerfile .

# 2. Inyectar al clúster
k3d image import personal_ai_api:latest personal_ai_worker:latest personal_ai_airflow:latest -c mycluster


Fase 7: Despliegue de Airflow (El Jefe Final)
Con la base de datos de Aiven fresca y los workers listos, desplegamos el orquestador usando la versión exacta y el archivo con los fixes de rutas y conexiones SQL.

PowerShell
helm repo add apache-airflow https://airflow.apache.org --force-update
helm repo update

helm install bmo-airflow apache-airflow/airflow --version 1.16.0 -n personal-ai -f k8s/airflow/helm-values.yaml

helm upgrade bmo-airflow apache-airflow/airflow --version 1.16.0 -n personal-ai -f k8s/airflow/helm-values.yaml --timeout 10m
 
🔍 Comprobación de Salud Final
Espera un par de minutos a que los componentes de Airflow ejecuten sus migraciones iniciales y monitorea todo el clúster con:

PowerShell
kubectl get pods -n personal-ai -w
Cuando veas que la API, el Scheduler de Airflow y el Webserver dicen 1/1 Running, abre tu navegador en http://localhost:8081/airflow (o en http://localhost:8081/ para tu API). Todo el sistema debería estar 100% operativo, con las redes saneadas y listo para ejecutar los tests de LangGraph.


kubectl logs -n personal-ai -l component=webserver --follow
kubectl logs -n personal-ai -l component=scheduler --follow
kubectl logs -n personal-ai -l component=worker --follow
kubectl logs -n personal-ai -l component=pgbouncer --follow
