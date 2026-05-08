# Reporte de Prueba: Oracle Cloud Object Storage

Se intentó verificar la conexión y escritura hacia el bucket `bronze` en OCI usando un script de prueba que replica la lógica de `DataLakeProvider` con el parche de `ContentLength`.

### Comando Ejecutado
Para ejecutar la prueba directamente en el worker de Airflow (que posee las credenciales en su entorno):

```powershell
Get-Content oracle_test_final.py | kubectl exec -i bmo-airflow-worker-0 -n personal-ai -c worker -- python -
```

### Script Utilizado (`oracle_test_final.py`)
El script fuerza el uso de `path-style` y el encabezado `ContentLength` de forma manual:

```python
import pandas as pd
import io
import os
import fsspec

# ... (configuración de storage_options)
storage_options = {
    "key": os.getenv("OCI_ACCESS_KEY"),
    "secret": os.getenv("OCI_SECRET_KEY"),
    "client_kwargs": {"endpoint_url": os.getenv("LAKEHOUSE_S3_ENDPOINT")},
    "config_kwargs": {"s3": {"addressing_style": "path"}},
    "s3_additional_kwargs": {"ContentLength": len(data)}
}

fs = fsspec.filesystem("s3", **storage_options)
fs.pipe_file("s3://bronze/test_final.parquet", data)
```

### Error Persistente
A pesar de forzar el `Content-Length`, OCI responde con un error 411 (Length Required), el cual `s3fs` traduce como:

```text
OSError: [Errno 22] The Content-Length header is required
botocore.exceptions.ClientError: An error occurred (MissingContentLength) when calling the PutObject operation: The Content-Length header is required
```

### Hallazgo Importante
Durante las pruebas manuales con `requests`, se detectó que los buckets originales (`bronze`, `silver`, `gold`, `warehouse`) **no existían** en el namespace de OCI. Se procedió a crearlos exitosamente vía script, pero el error de `Content-Length` persiste en la capa de transporte (`botocore`/`s3fs`).

> [!WARNING]
> El error `MissingContentLength` en OCI suele indicar que el cliente está enviando `Transfer-Encoding: chunked`, lo cual OCI no soporta para S3 `PutObject`. Es posible que se requiera una configuración de red o de versión de librería específica en la imagen de Airflow para forzar el envío del header.
