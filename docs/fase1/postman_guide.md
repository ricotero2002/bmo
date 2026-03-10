# Guía para Probar los Endpoints con Postman

Esta guía detalla cómo configurar y ejecutar pruebas en los endpoints de nuestra API, `/api/ingest` y `/api/query`, usando Postman. 

Asumimos que tu aplicación está corriendo mediante Docker en `http://localhost:8000`. Si el puerto es otro (ej. `8080`), simplemente ajusta la URL.

---

## 1. Probar el Endpoint de Ingesta (`/api/ingest`)

Este endpoint se utiliza para subir documentos (PDF, DOCX, XLSX, TXT, etc.) para que sean procesados, extraídos usando `MarkItDown` y guardados en la base de datos vectorial ChromaDB.

### Configuración en Postman:

1. **Método HTTP:** `POST`
2. **URL:** `http://localhost:8000/api/ingest`
3. **Pestaña `Body`:**
   - Selecciona la opción **`form-data`**.
   - En la columna **KEY**, escribe: `file`
   - Al pasar el cursor sobre la celda `file`, aparecerá un menú desplegable a la derecha que dice "Text". **Cámbialo a "File"**.
   - En la columna **VALUE**, aparecerá un botón que dice **"Select Files"**. Haz clic ahí y elige un archivo de tu computadora (por ejemplo, un documento `.pdf` o `.docx` de prueba).
4. **Haz clic en el botón azul `Send`.**

### Respuesta Esperada (JSON):
Si todo va bien, deberías recibir una respuesta `200 OK` con un JSON similar a este:
```json
{
    "status": "success",
    "filename": "mi_documento.pdf",
    "chunks_created": 15,
    "index_result": {
        "num_added": 15,
        "num_updated": 0,
        "num_skipped": 0,
        "num_deleted": 0
    }
}
```

---

## 2. Probar el Endpoint de Consulta (`/api/query`)

Este endpoint acepta una pregunta y busca en la base de datos vectorial los "chunks" (fragmentos) más relevantes del texto que ingeriste en el paso anterior. 

### Configuración en Postman:

1. **Método HTTP:** `POST`
2. **URL:** `http://localhost:8000/api/query`
3. **Pestaña `Body`:**
   - Selecciona la opción **`raw`**.
   - Justo a la derecha de `raw`, asegúrate de que el formato de texto esté configurado como **`JSON`** (por defecto suele decir `Text`).
   - Pega el siguiente JSON en el cuadro de texto grande:
     ```json
     {
         "query": "¿De qué trata el documento que acabo de subir?"
     }
     ```
4. **Haz clic en el botón azul `Send`.**

### Respuesta Esperada (JSON):
Deberías recibir una respuesta `200 OK` que incluye el contexto de los documentos extraídos por la base de datos según tu pregunta:
```json
{
    "context": [
        "Aquí va a aparecer el primer párrafo o chunk del texto más relevante de tu documento...",
        "Aquí aparecerá el segundo chunk más relevante..."
    ]
}
```

---

## Notas Adicionales y Tips para Postman

* **Importar como cURL:** Si prefieres, puedes usar la opción de Postman `File > Import > Raw text` e importar estos comandos directamente y Postman creará las solicitudes por ti:
  
  **Para Ingest:**
  ```bash
  curl --location 'http://localhost:8000/api/ingest' \
  --form 'file=@"/ruta/absoluta/a/tu/archivo.pdf"'
  ```

  **Para Query:**
  ```bash
  curl --location 'http://localhost:8000/api/query' \
  --header 'Content-Type: application/json' \
  --data '{
      "query": "¿Qué es RAG?"
  }'
  ```

* **Guardar las peticiones:** Te recomiendo hacer clic en **"Save"** dentro de Postman y crear una *Collection* llamada "Mi AI Assistant" para no tener que configurar esto la próxima vez que reinicies el servidor.
