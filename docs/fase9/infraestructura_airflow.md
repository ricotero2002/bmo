# Documentación de Infraestructura: Airflow + PgBouncer + Infisical

Este documento resume la arquitectura final de conectividad y seguridad implementada para estabilizar Airflow en k3d con base de datos externa (Aiven).

## 1. Mapa de Secretos Requeridos
Para que el clúster sea funcional desde cero, estos son los secretos que deben existir en el namespace `personal-ai`.

| Secreto | Tipo | Origen | Propósito |
| :--- | :--- | :--- | :--- |
| `app-secrets` | Opaque | Infisical | Contiene todas las credenciales de la app y del Broker (RabbitMQ/Redis). |
| `airflow-metadata` | Opaque | Manual | Contiene la URL de conexión principal a Postgres. |
| `airflow-pgbouncer-config` | Opaque | Infisical | Contiene los archivos `pgbouncer.ini` y `users.txt` generados dinámicamente. |
| `airflow-pgbouncer-stats` | Opaque | Manual | URL especial para que el monitor de métricas lea a PgBouncer. |
| `bmo-airflow-fernet-key` | Opaque | Chart | Clave de cifrado interna de Airflow. |

---

## 2. Arquitectura de PgBouncer: ¿Cómo funciona ahora?

Antes de este cambio, cada pod de Airflow intentaba "hablar" directamente con Aiven. Con muchos pods, superábamos el límite de conexiones (20) rápidamente.

**Ahora el flujo es:**
1. **Airflow (Client)**: El Scheduler, Worker y Webserver se conectan a `bmo-airflow-pgbouncer:6543`. Para ellos, PgBouncer *es* la base de datos.
2. **PgBouncer (Multiplexor)**: PgBouncer recibe las peticiones. Si tiene una conexión libre hacia Aiven, la usa. Si no, encola la petición durante milisegundos hasta que una conexión real se libere.
3. **Aiven (Server)**: Solo ve un máximo de **10 conexiones reales** provenientes de PgBouncer, sin importar cuántas tareas esté ejecutando Airflow simultáneamente.

---

## 3. Optimización de Pool de Conexiones (`SQL_ALCHEMY_POOL_SIZE`)

Al usar PgBouncer, ya no tenemos que ser tan restrictivos con el pool interno de Airflow. He ajustado los valores en `helm-values.yaml` para aprovechar el multiplexado:

*   **`AIRFLOW__DATABASE__SQL_ALCHEMY_POOL_SIZE`**: Aumentado a **5**.
    *   Cada pod (Scheduler, Worker, Webserver) puede mantener 5 conexiones "virtuales" abiertas hacia PgBouncer.
*   **`AIRFLOW__DATABASE__SQL_ALCHEMY_MAX_OVERFLOW`**: Aumentado a **2**.
    *   Permite ráfagas de hasta 7 conexiones por pod en momentos de pico de trabajo.

**Total teórico**: 3 pods x 7 conexiones = 21 conexiones virtuales.
**Impacto real**: PgBouncer las reducirá a un máximo de 10 conexiones físicas contra Aiven, manteniendo la base de datos siempre disponible.

---

## 4. Flujo de Infisical (Resumen de Seguridad)
1. Los secretos se guardan en el panel de Infisical.
2. Usamos **interpolación** (`${AIVEN_PG_HOST}`) para que los archivos de configuración de PgBouncer se generen solos sin hardcodear nada.
3. El **Infisical Operator** detecta cambios en la nube y actualiza los secretos de Kubernetes automáticamente.
4. Airflow y PgBouncer recargan la configuración (o se reinician) con los datos frescos.
