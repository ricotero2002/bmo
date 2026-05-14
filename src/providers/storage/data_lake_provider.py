import os
import io
import gc
import logging
import pandas as pd
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataLakeProvider:
    """
    Abstracción para almacenamiento en Oracle Object Storage via S3-compatible API.

    Usa boto3 directamente (NO fsspec/s3fs) porque OCI rechaza uploads sin
    Content-Length explícito, que es lo que fsspec hace por defecto en modo streaming.

    Variables de entorno requeridas:
      OCI_NAMESPACE    — Namespace del Object Storage (OCI Console → Object Storage)
      OCI_REGION       — Región, ej. "us-ashburn-1"
      OCI_BUCKET_NAME  — Bucket principal (ej. "bronze")
      OCI_ACCESS_KEY   — Customer Secret Key ID
      OCI_SECRET_KEY   — Customer Secret Key
    """

    def __init__(self):
        self.access_key = os.getenv("OCI_ACCESS_KEY")
        self.secret_key = os.getenv("OCI_SECRET_KEY")
        self.region = os.getenv("OCI_REGION", "us-ashburn-1")
        self.namespace = os.getenv("OCI_NAMESPACE")
        self.default_bucket = os.getenv("OCI_BUCKET_NAME", "bronze")

        if not all([self.access_key, self.secret_key, self.namespace]):
            raise ValueError(
                "Faltan variables de entorno de OCI: "
                "OCI_ACCESS_KEY, OCI_SECRET_KEY, OCI_NAMESPACE"
            )

        self.endpoint_url = (
            f"https://{self.namespace}.compat.objectstorage.{self.region}.oraclecloud.com"
        )

        # OCI requiere:
        # 1. Firma S3v4
        # 2. payload_signing_enabled=True  → evita Transfer-Encoding: chunked
        # 3. addressing_style="path"       → OCI no soporta virtual-hosted style
        try:
            boto_config = Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                s3={
                    "payload_signing_enabled": True,
                    "addressing_style": "path",
                },
                # botocore >=1.34 añade checksums automáticos; OCI no los soporta
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            )
        except TypeError:
            # Fallback para versiones antiguas de botocore
            boto_config = Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                s3={
                    "payload_signing_enabled": True,
                    "addressing_style": "path",
                },
            )

        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            config=boto_config,
        )

        logger.info(
            f"DataLakeProvider iniciado → endpoint: {self.endpoint_url} | "
            f"bucket por defecto: {self.default_bucket}"
        )

    # ─────────────────────────────────────────────
    # ESCRITURA
    # ─────────────────────────────────────────────

    def write_parquet_chunk(
        self,
        df: pd.DataFrame,
        zone: str,
        table_name: str,
        partition_date: str,
        chunk_idx: int,
    ) -> str:
        """
        Serializa el DataFrame a Parquet en memoria y lo sube a OCI con boto3.
        Content-Length se calcula antes del upload para cumplir con OCI.

        Retorna la ruta s3://bucket/... del objeto creado.
        """
        # Usamos siempre el bucket principal y la zona como prefijo
        bucket = self.default_bucket
        prefix = f"{zone}/" if zone else ""
        object_key = f"{prefix}{table_name}/date={partition_date}/chunk_{chunk_idx}.parquet"
        s3_uri = f"s3://{bucket}/{object_key}"

        logger.info(f"Serializando chunk {chunk_idx} ({len(df)} filas) → {s3_uri}")

        buffer = io.BytesIO()
        try:
            df.to_parquet(buffer, index=False, engine="pyarrow", compression="snappy")
            parquet_bytes = buffer.getvalue()
            size_kb = len(parquet_bytes) / 1024

            logger.info(f"Subiendo {size_kb:.2f} KB a OCI...")

            # put_object de boto3 incluye Content-Length automáticamente cuando
            # Body es bytes — OCI acepta esto sin problemas.
            self.client.put_object(
                Bucket=bucket,
                Key=object_key,
                Body=parquet_bytes,
                ContentLength=len(parquet_bytes),
                ContentType="application/octet-stream",
            )

            logger.info(f"✅ Chunk {chunk_idx} guardado en {s3_uri} ({size_kb:.2f} KB)")
            return s3_uri

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(f"❌ OCI ClientError [{error_code}] escribiendo {s3_uri}: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Error inesperado escribiendo {s3_uri}: {e}")
            raise
        finally:
            buffer.close()
            del buffer
            del df
            gc.collect()

    # ─────────────────────────────────────────────
    # LECTURA
    # ─────────────────────────────────────────────

    def read_parquet_partition(
        self,
        zone: str,
        table_name: str,
        partition_date: str,
    ) -> pd.DataFrame:
        """
        Lee todos los chunks Parquet de una partición y los devuelve como un único DataFrame.
        Útil para tareas de validación o debugging sin Spark.
        """
        bucket = self.default_bucket
        zone_prefix = f"{zone}/" if zone else ""
        prefix = f"{zone_prefix}{table_name}/date={partition_date}/"

        logger.info(f"Listando objetos en s3://{bucket}/{prefix}")

        paginator = self.client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

        frames = []
        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".parquet"):
                    continue
                response = self.client.get_object(Bucket=bucket, Key=key)
                body = response["Body"].read()
                frames.append(pd.read_parquet(io.BytesIO(body)))

        if not frames:
            logger.warning(f"⚠️ No se encontraron archivos Parquet en s3://{bucket}/{prefix}")
            return pd.DataFrame()

        df = pd.concat(frames, ignore_index=True)
        logger.info(f"✅ Leídas {len(df)} filas desde {len(frames)} chunks")
        return df

    def list_partition_files(self, zone: str, table_name: str, partition_date: str) -> list:
        """Lista las claves S3 de una partición."""
        bucket = self.default_bucket
        zone_prefix = f"{zone}/" if zone else ""
        prefix = f"{zone_prefix}{table_name}/date={partition_date}/"
        paginator = self.client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
        keys = [
            obj["Key"]
            for page in pages
            for obj in page.get("Contents", [])
        ]
        logger.info(f"Archivos en s3://{bucket}/{prefix}: {keys}")
        return keys
