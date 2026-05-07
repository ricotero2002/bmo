# 🚀 Guía de Exportación e Importación de Imágenes a K3s

Para que Kubernetes (específicamente K3d o K3s local) pueda ver tus imágenes personalizadas sin usar un registro externo (Docker Hub), debes seguir este flujo de trabajo.

## 1. Generar Imágenes (Build)

Ejecuta estos comandos desde la raíz del proyecto `d:\BMO\bmo`:

```powershell
# API (FastAPI)
docker build --target final-api -t personal_ai_api:latest -f docker/Dockerfile .

# Worker (Celery)
docker build --target final-worker -t personal_ai_worker:latest -f docker/Dockerfile .

# Airflow (Custom con Java)
docker build -t personal_ai_airflow:latest -f data_tooling/airflow/Dockerfile .
```

## 2. Importar al Clúster (K3d)

Una vez generadas, las imágenes viven en tu Docker local, pero el clúster K3d no las ve automáticamente. Debes "inyectarlas":

```powershell
# Importar una por una
k3d image import personal_ai_api:latest -c mycluster;
k3d image import personal_ai_worker:latest -c mycluster;
k3d image import personal_ai_airflow:latest -c mycluster;

k3d image import personal_ai_api:latest personal_ai_worker:latest personal_ai_airflow:latest -c mycluster

```

> [!TIP]
> Si el nombre de tu clúster no es `mycluster`, puedes verificarlo con `k3d cluster list`.

## 3. Desplegar en Kubernetes

Asegúrate de que tus manifiestos tengan `imagePullPolicy: Never` o `IfNotPresent` para que K8s no intente descargarlas de internet:

```yaml
spec:
  containers:
  - name: api
    image: personal_ai_api:latest
    imagePullPolicy: Never  # <--- VITAL
```

helm upgrade bmo-airflow apache-airflow/airflow --version 1.16.0 -n personal-ai -f k8s/airflow/helm-values.yaml

# Reiniciar Deployments
kubectl rollout restart deployment/bmo-airflow-scheduler -n personal-ai
kubectl rollout restart deployment/bmo-airflow-webserver -n personal-ai

# Reiniciar StatefulSets (Workers y Triggerer)
kubectl rollout restart statefulset/bmo-airflow-worker -n personal-ai
kubectl rollout restart statefulset/bmo-airflow-triggerer -n personal-ai

## 4. Troubleshooting: "ErrImageNeverPull"

Si ves este error al hacer `kubectl get pods`, significa que:
1. Olvidaste hacer el `k3d image import`.
2. El tag de la imagen en el YAML no coincide exactamente con el tag en Docker (ej. `latest` vs `v1`).
3. El clúster se reinició y perdió la cache (poco común en k3d).

**Solución rápida:**
```powershell
k3d image import personal_ai_api:latest -c mycluster
kubectl rollout restart deployment/api-deployment -n personal-ai
```
