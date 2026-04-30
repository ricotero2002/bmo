# Guía Completa: Cómo Sincronizar Notion con BMO

Esta guía explica paso a paso cómo un usuario puede conectar su base de conocimientos o base de datos de Notion con nuestro Agente BMO para que sea ingerida y procesada automáticamente.

---

## 1. Crear una Integración en Notion y obtener el Token

Para que BMO pueda leer tus datos, necesitas crear una "Integración" (App interna) en tu espacio de Notion.

1. Ve a [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations) e inicia sesión.
2. Haz clic en el botón **"New integration"** (Nueva integración).
3. Selecciona el espacio de trabajo donde está la base de datos que quieres sincronizar y dale un nombre (ej. `BMO Sync`).
4. Haz clic en **Submit** (Enviar).
5. Notion te mostrará un **Internal Integration Secret** (Token Secreto). Cópialo y guárdalo en un lugar seguro.
   - *Ejemplo de token: `secret_xYzaB123...`*

---

## 2. Obtener el ID de la Base de Datos a sincronizar

BMO necesita saber exactamente qué base de datos (o página) leer de todo tu Notion.

1. Entra a tu espacio de Notion desde el navegador (o copia el link desde la app).
2. Ve a la Base de Datos o página principal que quieres indexar.
3. Copia la URL del navegador. Tendrá un formato como este:
   `https://www.notion.so/workspace/1234567890abcdef1234567890abcdef?v=...`
4. El **Database ID** es la serie de 32 caracteres y números que está *después* del nombre de tu espacio de trabajo y *antes* del signo `?v=`.
   - *Para el ejemplo superior, el ID es: `1234567890abcdef1234567890abcdef`*

---

## 3. ¡IMPORTANTE! Darle permisos a la Integración

Por defecto, la integración que creaste en el paso 1 no tiene acceso a nada por cuestiones de privacidad. Debes invitar a la integración a tu base de datos:

1. Ve a la base de datos de Notion que elegiste en el paso 2.
2. Haz clic en los **tres puntos (`...`)** en la esquina superior derecha de la pantalla.
3. Busca la opción **"Add connections"** (Añadir conexiones) o **"Connections"**.
4. Busca el nombre de tu integración (ej. `BMO Sync`) y selecciónala para darle acceso.

---

## 4. Registrar la Integración en BMO

Una vez que tienes el **Token** y el **Database ID**, solo queda avisarle a la API de BMO que quieres registrar esta integración.

Puedes hacerlo disparando una petición `POST` al endpoint que construimos. A continuación, un ejemplo usando `curl` (o puedes usar Postman / Swagger):

```bash
curl -X POST "http://localhost:8000/api/integrations/notion/register" \
     -H "Content-Type: application/json" \
     -d '{
           "user_id": "tu_usuario_123",
           "access_token": "secret_xYzaB123...",
           "database_id": "1234567890abcdef1234567890abcdef"
         }'
```

**¿Qué ocurre al enviar esto?**
- BMO tomará tu `access_token` y tu `database_id` y los **encriptará (AES-256)** usando la llave segura de la base de datos.
- BMO anotará tu usuario en el sistema de sincronización (`IngestionSyncState`) con estado "Pendiente".

---

## 5. La Sincronización Mágica (Airflow)

A partir de que registras la base de datos, ¡ya no tienes que hacer nada más!

1. **Full Load (Carga Inicial):** Al día siguiente (o cuando se dispare el DAG de Airflow), el orquestador verá tu registro. Como es la primera vez, descargará *toda* tu base de datos de Notion, la empaquetará, y la enviará al Storage y posteriormente al clúster de Spark/Celery para convertirla en Embeddings.
2. **Change Data Capture (CDC):** BMO guardará la fecha exacta de esta sincronización exitosa. Las veces siguientes, Airflow sólo le preguntará a Notion: *"¿Qué documentos han cambiado desde la última vez?"*. Esto ahorra tiempo y dinero, descargando solo tus modificaciones o nuevas notas.
