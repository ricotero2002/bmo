# Guía de Debugging en Kubernetes (K8s)

Este documento centraliza los comandos y estrategias para diagnosticar problemas en el cluster, especialmente con Airflow y dbt.

## 1. El comando Maestro: `kubectl exec`
Permite ejecutar comandos directamente dentro de un contenedor en ejecución. Es como un SSH para Docker.

### Estructura General
```powershell
kubectl exec -n <namespace> <nombre-pod> -c <contenedor> -- sh -c '<comando>'
```

---

## 2. Comandos Útiles de dbt
Para verificar conectividad y permisos desde el worker o scheduler de Airflow:

### 🚨 Fix de Permisos "In-Vivo" (Temporal)
Si dbt falla con `PermissionError` y no puedes reconstruir la imagen ahora, corre esto para abrir los permisos en el pod actual:
```powershell
# En el Scheduler
kubectl exec -n personal-ai $(kubectl get pods -n personal-ai -l component=scheduler -o name) -c scheduler -- sh -c 'chmod -R 777 /opt/airflow/dbt/logs /opt/airflow/dbt/target 2>/dev/null; mkdir -p /opt/airflow/dbt/logs /opt/airflow/dbt/target && chmod 777 /opt/airflow/dbt/logs /opt/airflow/dbt/target'

# En el Worker (si existe)
kubectl exec -n personal-ai bmo-airflow-worker-0 -c worker -- sh -c 'mkdir -p /opt/airflow/dbt/logs /opt/airflow/dbt/target && chmod 777 /opt/airflow/dbt/logs /opt/airflow/dbt/target'
```

### Verificar Conexión y Perfiles (`dbt debug`)
```powershell
kubectl exec -n personal-ai $(kubectl get pods -n personal-ai -l component=scheduler -o name) -c scheduler -- sh -c 'cd /opt/airflow/dbt && dbt debug --profiles-dir /opt/airflow/dbt --target-path /tmp/dbt_target --log-path /tmp/dbt_logs'
```
*   **`--log-path /tmp/dbt_logs`**: Redirige los logs a un lugar escribible si el fix de permisos no se aplicó.

---

## 3. Manejo de Logs
```powershell
# Listar logs
kubectl exec -n personal-ai bmo-airflow-worker-0 -c worker -- ls -R /tmp/dbt_logs

# Leer log
kubectl exec -n personal-ai bmo-airflow-worker-0 -c worker -- cat /tmp/dbt_logs/dbt.log
```

---

## 4. Modo Interactivo
```powershell
kubectl exec -it -n personal-ai bmo-airflow-worker-0 -c worker -- bash
```
