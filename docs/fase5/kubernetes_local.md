# Guía: Pruebas Locales con Kubernetes (k3d) y KEDA

Esta guía detalla cómo separar la **Infraestructura** (que mantendremos en Docker Compose para ahorrar memoria) de las **Aplicaciones** (que migrarán a un clúster local de Kubernetes para poder probar el autoescalado con KEDA).

## 1. Instalación de Herramientas (Setup Local)

Para este entorno híbrido, necesitarás instalar:

- **k3d**: Distribución ligera de Kubernetes que corre sobre la infraestructura de Docker.
  ```bash
  curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | TAG=v5.6.0 bash
  ```
  *(En Windows, si usas WSL2, puedes correr este mismo comando. Si usas PowerShell nativo y tienes Chocolatey, usa: `choco install k3d`)*
- **kubectl**: CLI oficial de Kubernetes.
  *(Windows/Chocolatey: `choco install kubernetes-cli`, Linux/WSL: `sudo apt-get install kubectl`)*
- **Helm**: Gestor de paquetes de Kubernetes usado para instalar herramientas adicionales como KEDA.
  *(Windows/Chocolatey: `choco install kubernetes-helm`, Linux/WSL: `curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash`)*
- **Tilt** *(Opcional)*: Herramienta excelente para recompilar y desplegar pods automáticamente al guardar un cambio en un archivo de tu PC.

---

## 2. Estructura de Carpetas Sugerida

Para mantener tu repositorio ordenado, es buena idea crear una nueva carpeta especial para las configuraciones de Kubernetes:

```text
personal-ai-assistant/
├── docker/
│   └── docker-compose.yml   <-- ¡Modificar! Aquí dejarás SOLO la infraestructura (Bases de datos/Colas)
├── k8s/                     <-- NUEVA CARPETA (Créala en el root del proyecto)
│   ├── apps-deployment.yaml <-- Manifiestos de FastAPI y Celery Worker
│   └── keda-scaler.yaml     <-- Configuración del Trigger de KEDA
└── ...
```

### Modificación de `docker-compose.yml`
Ve a tu archivo `docker-compose.yml` base y remueve (o comenta) la sección de las **aplicaciones de Python** (`api`, `worker`, etc.).
Solo deben quedar los servicios de persistencia y brokers: `postgres`, `redis`, `rabbitmq`, `kafka`, `chromadb`, `minio`. 
Asegúrate de que cada uno tenga configurada la sección `ports` porque Kubernetes (k3d) llegará a ellos consumiendo los puertos expuestos en tu localhost.

---

1. La Arquitectura de Tráfico (El Diseño)
Tanto en local como en OCI, la estructura será esta:
Internet —> Load Balancer (IP Pública) —> Ingress Controller (NGINX) —> Service (ClusterIP) —> Tus Pods (FastAPI)

¿Por qué así?
Porque en el Always Free de OCI, solo tienes un Load Balancer flexible de 10 Mbps. Si expones tu API con un service tipo LoadBalancer, ya gastaste tu único cartucho. Si luego quieres exponer un frontend o un dashboard de monitoreo, no podrías. Con un Ingress, ese único Load Balancer de Oracle le entrega todo el tráfico a NGINX, y NGINX reparte el juego internament

2. Implementación en Local (k3d)
En tu PC, el "Load Balancer" es tu propio router/localhost. Usaremos k3d porque ya trae un balanceador de carga integrado (basado en Klipper).

Paso a paso para instalar el Ingress en Local:

Crea el clúster mapeando puertos:

Bash
k3d cluster create mycluster -p "8081:80@loadbalancer" --agents 2
k3d cluster create mycluster -p "8081:80@loadbalancer"
Aquí le decimos: "Lo que llegue a mi puerto 8081, mándalo al puerto 80 del Load Balancer interno de Kubernetes".

Instala NGINX Ingress Controller:
k3d ya suele traer uno, pero para tener control total, es mejor instalar el oficial vía Helm:

Bash
helm upgrade --install ingress-nginx ingress-nginx \
  --repo https://kubernetes.github.io/ingress-nginx \
  --namespace ingress-nginx --create-namespace

3. Implementación en Oracle Cloud (OKE)
Cuando te pases a OCI, el archivo de Kubernetes (yaml) será 99% idéntico. Solo cambiará la forma en que el Service pide el Load Balancer a Oracle.

Cómo configurar el Service para el Always Free de OCI:

Para que Oracle no te cobre y use el de 10 Mbps gratuito, el Service de tu Ingress Controller debe tener estas anotaciones:

YAML
# Este fragmento va en la configuración del Service de NGINX en OCI
metadata:
  annotations:
    # Selecciona el tipo de LB flexible
    oci.oraclecloud.com/load-balancer-type: "lb"
    # Fuerza el ancho de banda al límite gratuito
    service.beta.kubernetes.io/oci-load-balancer-shape: "10Mbps"
4. Conexión Local vs. OCI (El puente de Red)
Aquí es donde resolvemos el problema de "cómo conectar Kubernetes con mis bases de datos que siguen en Docker".

En Local (k3d + Docker Compose):
Para que tu Pod de FastAPI vea al Postgres que está en Docker, usaremos un Endpoint y un Service manual en Kubernetes que apunte a la IP de tu máquina.

Crea este archivo external-services.yaml:

YAML
kind: Service
apiVersion: v1
metadata:
  name: postgres-db # El nombre que usará tu código (DB_HOST=postgres-db)
spec:
  ports:
  - protocol: TCP
    port: 5432
---
kind: Endpoints
apiVersion: v1
metadata:
  name: postgres-db
subsets:
  - addresses:
      - ip: 172.17.0.1 # IP por defecto de la interfaz docker0 en Linux
    ports:
      - port: 5432

## 3. Archivos K8s a Crear

Crea estos dos archivos dentro de la nueva carpeta `k8s/`:

### Archivo 1: `k8s/apps-deployment.yaml`

Agrupa el namespace, servicio, ingress y deployments de la API y el celular worker:

```yaml
# 1. Namespace para organizar todo
apiVersion: v1
kind: Namespace
metadata:
  name: personal-ai

---
# 2. Service Interno para FastAPI
apiVersion: v1
kind: Service
metadata:
  name: api-service
  namespace: personal-ai
spec:
  type: ClusterIP # Solo visible dentro del clúster
  selector:
    app: api
  ports:
    - port: 80
      targetPort: 8000

---
# 3. Ingress: La puerta de entrada al clúster
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-ingress
  namespace: personal-ai
  annotations:
    ingress.kubernetes.io/ssl-redirect: "false"
spec:
  rules:
  - http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: api-service
            port:
              number: 80

---
# 4. Deployment de FastAPI
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-deployment
  namespace: personal-ai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: personal_ai_api:latest # Tu imagen compilada
        imagePullPolicy: Never # Importante para usar imágenes locales importadas
        ports:
        - containerPort: 8000
        envFrom:
        - secretRef:
            name: app-secrets # Sincronizado vía Infisical o Secret Genérico
        env:
        - name: DB_HOST
          value: "host.k3d.internal" # Apunta al host de Docker (donde habita tu Compose)
        - name: RABBITMQ_URL
          value: "pyamqp://guest:guest@host.k3d.internal:5672//"

---
# 5. Deployment del Worker (Lo que KEDA va a escalar)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: worker-deployment
  namespace: personal-ai
spec:
  replicas: 1 # KEDA manejará esto una vez instalado
  selector:
    matchLabels:
      app: worker
  template:
    metadata:
      labels:
        app: worker
    spec:
      containers:
      - name: worker
        image: personal_ai_api:latest
        command: ["celery", "-A", "src.workers.tasks", "worker", "--loglevel=info"]
        envFrom:
        - secretRef:
            name: app-secrets
        env:
        - name: RABBITMQ_URL
          value: "pyamqp://guest:guest@host.k3d.internal:5672//"
```

### Archivo 2: `k8s/keda-scaler.yaml`

El archivo de "Magia". Le dice a Kubernetes cómo tiene que leer tu cola y cuándo pedir réplicas del deployment.

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: celery-worker-scaler
  namespace: personal-ai
spec:
  scaleTargetRef:
    name: worker-deployment # A quién vamos a escalar (Deployment que creamos antes)
  minReplicaCount: 0  # <--- MAGIA: Escala a cero si no hay trabajo (Ahorras RAM)
  maxReplicaCount: 5
  triggers:
  - type: rabbitmq
    metadata:
      queueName: celery # El nombre de la cola en RabbitMQ
      host: amqp://guest:guest@host.k3d.internal:5672/
      queueLength: "5" # Cada 5 mensajes encolados, pide iniciar un Pod adicional
```

kubectl create secret generic infisical-auth-secret \
  --from-literal=client-id="TU_IDENTITY_ID" \
  --from-literal=client-secret="TU_CLIENT_SECRET" \
  -n personal-ai

---

## 4. Paso a Paso: Ejecución Local

Con los archivos creados, haz lo siguiente en este exacto orden:

### 1. Inicia la Infraestructura (Docker Compose)
Levanta los contenedores pesados.
```bash
docker compose up -d postgres redis rabbitmq kafka chromadb minio
```

### 2. Crea el clúster k3d
Mapeamos el puerto interno 80 de Loadbalancer hacia tu localhost 8081. Así podrás probar la API.
```bash
k3d cluster create mycluster --api-port 6443 -p "8081:80@loadbalancer" --agents 2
```

### 3. Instala KEDA usando Helm
Agrega el repo oficial e instálalo dentro del clúster recién creado.
```bash
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda --namespace keda --create-namespace
```

### 4. Compila la(s) Imagen(es) de tu Código
No puedes apuntar K8s a tus carpetas locales como en Docker Compose, debes empaquetar el código primero.
```bash
# Asumiendo que tu Dockerfile se llama Dockerfile.api y está en una subcarpeta
docker build -t personal_ai_api:latest -f docker/Dockerfile.api .
```

### 5. Carga las Imágenes en el Clúster
Como elegimos la política `imagePullPolicy: Never`, necesitamos inyectar manualmente la imagen dentro del registro del clúster k3d para que sepa de dónde sacarla.
```bash
k3d image import personal_ai_api:latest -c mycluster
```

*(Si utilizas variables de entorno secretas, asegúrate de crear el Secret `app-secrets` dentro del clúster: `kubectl create namespace personal-ai && kubectl create secret generic app-secrets --from-env-file=.env -n personal-ai`)*

### 6. Aplica tus Manifiestos
Aplica primero la app y finalmente las reglas de autoescalado.
```bash
kubectl apply -f k8s/apps-deployment.yaml
kubectl apply -f k8s/keda-scaler.yaml
```

---

## 5. Explicación de Conectividad `host.k3d.internal`

En esta arquitectura híbrida (App en K8s, Infra en Compose), tus microservicios de Kubernetes intentan salir para consultar a la base de datos de Docker. 

K3D mapea automáticamente la ruta `host.k3d.internal` hacia el `localhost` del sistema operativo host (es decir, tu computadora real). 

Para que los Pods se enganchen sin error al PostgreSQL de Docker, es mandatorio que el Docker Compose exponga los puertos (tenga la cláusula `ports: - "5432:5432"`, `ports: - "5672:5672"`). Si desde una consola de tu computadora pruebas conectarte a `localhost:5432` y funciona exitosamente, K3D podrá enrutarse correctamente usando `host.k3d.internal`.

Si esto falla en la práctica, otra opción más directa es omitir el uso de `host.k3d.internal` y hacer que k3d **se una directamente a la red de tu docker-compose** usando un flag durante la creación del cluster:
```bash
k3d cluster create mycluster ... --network nombre_del_puente_de_compose
```
Si haces esto, podrías referenciar tus bases de datos por sus nombres locales (ej `postgres:5432`). Recomiendo empezar por la primera técnica por simplicidad en tu SO.

---

### ¡Comprobación!
Si mandas tráfico hacia la API alojada en K8s `localhost:8081`, Kafka y RabbitMQ registrarán los mensajes, y abriendo un terminal paralelo puedes ver la magia de KEDA escalando tu worker:
```bash
kubectl get pods -n personal-ai -w
```
(El flag `-w` deja la terminal abierta observando cambios en tiempo real).


1. El comando mágico de k3d
Ejecutá esto en tu terminal para exportar la configuración del clúster de k3d a tu archivo de configuración principal de Kubernetes:

Bash
k3d kubeconfig merge mycluster -d -s
(Cambiá mycluster por el nombre que le pusiste al crear el clúster).

Este comando hace dos cosas:

Copia las credenciales (certificados e IPs) a tu archivo ~/.kube/config.

Setea ese clúster como el "activo" en tu terminal.

2. Verificar en Lens
Una vez que corras ese comando, hacé lo siguiente en Lens:

Hacé clic en el icono de "Catalog" (el que parece un librito o lista) en la barra lateral izquierda.

Buscá en la pestaña "Clusters". Debería aparecer uno llamado k3d-mycluster.

Hacé clic en él para conectar.

1. Levantar la Infraestructura Base (Docker)

bash
docker compose up -d
2. Crear el clúster k3d (si no lo has hecho)

bash
k3d cluster create mycluster --api-port 6443 -p "8081:80@loadbalancer" --agents 2
3. Compilar tu imagen y subirla al clúster Para que Kubernetes sepa qué es personal_ai_api:latest, compila e importa:

bash
docker build -t personal_ai_api:latest -f docker/Dockerfile .
k3d image import personal_ai_api:latest -c mycluster
4. Aplicar tus manifiestos en Kubernetes Primero aplica el ConfigMap y tu configuración de Secretos, y después los deployments:

bash
# Entorno base
kubectl apply -f k8s/app-configmap.yaml
kubectl apply -f k8s/infisical-config.yaml
# (Recuerda que también necesitas el Secret manual con las credenciales Identity de Infisical que anotaste en la guía anterior)
# Aplicaciones y KEDA
kubectl apply -f k8s/apps-deployment.yaml
kubectl apply -f k8s/keda-scaler.yaml



Los errores que estás viendo son súper comunes cuando se levanta un clúster de cero. Vamos a diagnosticar exactamente por qué pasaron antes de pasar a la guía:

1. **Error de Infisical (`no matches for kind "InfisicalSecret"`)**: Kubernetes, por defecto, no tiene ni idea de qué es un `InfisicalSecret`. Es un "Custom Resource" (Recurso Personalizado). Para que lo entienda, primero hay que instalar las **CRDs (Custom Resource Definitions)**, lo cual se logra instalando el Operador de Infisical en el clúster. Como el operador no estaba, Kubernetes rechazó tu archivo.
2. **Error de OpenTelemetry (`apiVersion not set, kind not set`)**: Intentaste usar `kubectl apply -f` con el archivo `otel-collector-values.yaml`. Ese archivo **no es un manifiesto de Kubernetes**, es un archivo de "Valores" para **Helm**. No se puede inyectar directo con `kubectl`, se tiene que pasar como parámetro al comando `helm install` o `helm upgrade`.

Aquí tienes la **guía paso a paso, en el orden estricto** en el que debes ejecutar las cosas para levantar tu clúster de K3D desde cero sin que nada falle.

---

### Fase 0: Limpieza total (Recomendado)
Si tu clúster actual está corrupto o a medias, lo mejor es matarlo y arrancar limpio.
```powershell
k3d cluster delete mycluster
```

### Fase 1: Infraestructura y Clúster Base
Primero levantamos las bases de datos en Docker y luego creamos el clúster vacío.

```powershell
# 1. Levantar bases de datos, Kafka, Redis, etc.
docker compose up -d

# 2. Crear el clúster de k3d
k3d cluster create mycluster --api-port 127.0.0.1:6443 -p "8081:80@loadbalancer"

# 3. Actualizar tu puntero de kubectl
k3d kubeconfig merge mycluster -d -s
```

### Fase 2: Instalar Operadores y CRDs (¡Soluciona el Error 1!)
Antes de meter tu aplicación, Kubernetes necesita aprender a leer recursos de KEDA e Infisical. Lo hacemos instalando sus operadores vía Helm.

```powershell
# 1. Instalar KEDA (Para el autoescalado)
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm upgrade --install keda kedacore/keda --namespace keda --create-namespace

# 2. Instalar Infisical Operator (Para que entienda los InfisicalSecret)
helm repo add infisical https://dl.cloudsmith.io/public/infisical/helm-charts/helm/charts/
helm repo update
helm upgrade --install infisical-operator infisical/secrets-operator --namespace infisical-operator-system --create-namespace

### Fase 3: Crear Namespaces y Secretos Manuales
Preparamos los "barrios" y metemos los secretos duros que necesitan existir antes del despliegue.

```powershell
# 1. Crear los namespaces
kubectl create namespace personal-ai
kubectl create namespace observability

# 2. Secreto de Kafka (Certificado CA)
kubectl create secret generic kafka-ca-cert --from-file=ca.pem=./ca.pem -n personal-ai

# 3. Secreto de Autenticación de Infisical (Reemplaza los valores con los tuyos)
kubectl create secret generic infisical-auth-secret `
  --from-literal=clientId="TU_CLIENT_ID_REAL" `
  --from-literal=clientSecret="TU_CLIENT_SECRET_REAL" `
  --namespace personal-ai

# 4. Secreto de Grafana Cloud para OpenTelemetry
kubectl create secret generic grafana-otel-secret `
  --from-literal=endpoint="https://otlp-gateway-prod-us-east-0.grafana.net/otlp" `
  --from-literal=auth="Basic TU_TOKEN_BASE64" `
  --namespace observability
```

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

### Fase 5: Compilar e Importar Imágenes
Construimos el código y se lo pasamos al cerebro de K3D.

```powershell
# 1. Build de las imágenes (API y Worker)
docker build --target final-api -t personal_ai_api:latest -f docker/Dockerfile .
docker build --target final-worker -t personal_ai_worker:latest -f docker/Dockerfile .

# 2. Importar al clúster
k3d image import personal_ai_api:latest personal_ai_worker:latest -c mycluster
```

### Fase 6: Despliegue Final de tu Aplicación
Ahora sí, Kubernetes ya tiene todas las herramientas, secretos y definiciones necesarias para leer tus manifiestos de producción.

```powershell
# 1. Variables de entorno no secretas
kubectl apply -f k8s/prod/app-configmap.yaml

# 2. Sincronización de secretos (Ahora sí funcionará porque instalaste el operador en la Fase 2)
kubectl apply -f k8s/prod/infisical-config.yaml

# 3. Desplegar los Pods (API, Celery Worker, Kafka Consumer)
kubectl apply -f k8s/prod/apps-deployment.yaml
kubectl apply -f k8s/prod/kafka-deployment.yaml

# 4. Reglas de Autoescalado
kubectl apply -f k8s/prod/keda-scaler.yaml
kubectl apply -f k8s/prod/api-hpa.yaml
```

### Fase 7: Verificación
```powershell
# Mirar cómo nacen los pods
kubectl get pods -n personal-ai -w
```