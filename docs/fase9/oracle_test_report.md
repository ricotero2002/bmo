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




--------------

2. Gestión Estricta de MemoriaCuando procesas muchos chunks en un bucle, Python a veces no libera la memoria lo suficientemente rápido (Garbage Collection). Forzar el cierre de buffers y eliminar referencias ayuda a mantener estable el uso de RAM.Así quedaría tu método write_parquet_chunk optimizado:pythonimport gc # Garbage Collector

def write_parquet_chunk(self, df: pd.DataFrame, zone: str, table_name: str, partition_date: str, chunk_idx: int):
    object_name = f"{table_name}/date={partition_date}/chunk_{chunk_idx}.parquet"
    
    # Usamos try/finally para asegurar que la memoria se limpie pase lo que pase
    buffer = io.BytesIO()
    try:
        # 1. Escribir al buffer
        df.to_parquet(buffer, index=False, engine='pyarrow', compression='snappy')
        buffer.seek(0)

        # 2. Subir
        self.upload_manager.upload_stream(
            namespace_name=self.namespace,
            bucket_name=zone,
            object_name=object_name,
            stream_resumable=buffer
        )
    finally:
        # 3. LIMPIEZA EXPLÍCITA
        buffer.close()     # Libera el stream de memoria
        del buffer         # Elimina la referencia
        del df             # Elimina el DataFrame localmente
        gc.collect()       # Fuerza al recolector de basura de Python
        
    return object_name
Use code with caution.3. Ajuste en tu función save_chunkPara que la eliminación del DataFrame funcione, también debemos aplicarla en la función que llama al proveedor:pythondef save_chunk(data, provider, ds, idx):
    df = pd.DataFrame(data)
    
    # ... logs ...

    provider.write_parquet_chunk(df, "bronze", "langsmith_raw", ds, idx)
    
    # Limpieza después de que el provider termine
    del df
    gc.collect() 
    logger.info(f"✅ Chunk {idx} guardado y memoria liberada.")
Use code with caution.¿Por qué esto es importante?En procesos tipo Celery que procesan miles de filas:Evitas el "OOM Kill": El sistema operativo mata procesos que consumen demasiada RAM. Sin del y gc.collect(), la memoria sube como una escalera con cada chunk.

Para usar la Opción B (Compatibilidad S3) con tus variables actuales (OCI_ACCESS_KEY y OCI_SECRET_KEY), el truco está en configurar s3fs para que se comporte exactamente como Oracle espera.El error principal en OCI con S3 suele ser el 411 Length Required. Para evitarlo, configuramos un buffer en memoria que calcula el tamaño antes de disparar la subida.Aquí tienes la clase ajustada para funcionar con tus variables de entorno:pythonimport os
import io
import gc
import pandas as pd
import fsspec
import logging

logger = logging.getLogger(__name__)

class DataLakeProvider:
    def __init__(self):
        # 1. Cargamos tus variables actuales
        self.access_key = os.getenv("OCI_ACCESS_KEY")
        self.secret_key = os.getenv("OCI_SECRET_KEY")
        self.region = os.getenv("OCI_REGION", "us-ashburn-1")
        self.namespace = os.getenv("OCI_NAMESPACE")
        self.bucket_name = os.getenv("OCI_BUCKET_NAME")
        
        # 2. Construimos el endpoint de compatibilidad S3 de Oracle
        # Formato: https://{namespace}.compat.objectstorage.{region}.oraclecloud.com
        self.endpoint = f"https://{self.namespace}.compat.objectstorage.{self.region}.oraclecloud.com"
        
        # 3. Configuración crítica para que s3fs funcione con OCI
        self.storage_options = {
            "key": self.access_key,
            "secret": self.secret_key,
            "client_kwargs": {
                "endpoint_url": self.endpoint,
                "region_name": self.region
            },
            "config_kwargs": {
                "s3": {
                    "addressing_style": "path", # Obligatorio para OCI S3 Compat
                    "signature_version": "s3v4"
                }
            }
        }
        
        logger.info(f"DataLakeProvider (S3 Mode) iniciado para el bucket: {self.bucket_name}")

    def write_parquet_chunk(self, df: pd.DataFrame, zone: str, table_name: str, partition_date: str, chunk_idx: int):
        """Escribe en OCI usando s3fs con gestión manual de buffer para evitar errores de tamaño."""
        bucket = zone or self.bucket_name
        file_path = f"s3://{bucket}/{table_name}/date={partition_date}/chunk_{chunk_idx}.parquet"
        
        buffer = io.BytesIO()
        try:
            # Convertimos a parquet en memoria
            df.to_parquet(buffer, index=False, engine='pyarrow', compression='snappy')
            content = buffer.getvalue() # Obtenemos el contenido total
            
            # fsspec usa s3fs internamente
            fs = fsspec.filesystem("s3", **self.storage_options)
            
            # Al escribir el contenido directo (no el buffer abierto), 
            # s3fs sabe el tamaño exacto y OCI no rechaza la petición.
            with fs.open(file_path, "wb") as f:
                f.write(content)
                
            logger.info(f"✅ Guardado en {file_path} | Tamaño: {len(content) / 1024:.2f} KB")
            return file_path

        except Exception as e:
            logger.error(f"❌ Error escribiendo en OCI (S3 Mode): {e}")
            raise
        finally:
            # Limpieza de memoria rigurosa
            buffer.close()
            del buffer
            del df
            gc.collect()


Resumen de lo que resolvimos hoy:
Problema	Solución
403 Forbidden en S3A (Hadoop AWS SDK v1)	Descarga via boto3 (que soporta payload signing v4) al /tmp local
SdkClientException: Unable to load region (SDK v2 de Iceberg)	os.environ.setdefault("AWS_REGION", region) en spark_utils.py
OOM / Exit 137	local[2] + buffer disk + 5Gi worker
Liveness Probe matando al worker	failureThreshold: 20, periodSeconds: 60
Worker activo cuando no hay tareas	KEDA con minReplicaCount: 0