"""
Test de conectividad OCI — Correr así:

  Get-Content oracle_test_final.py | kubectl exec -i bmo-airflow-worker-0 \
    -n personal-ai -c worker -- python -

Si ves "✅ ÉXITO" el DataLakeProvider está listo.
"""
import sys
sys.path.append("/opt/project")

from src.providers.storage.data_lake_provider import DataLakeProvider
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_oci():
    logger.info("=== Test de conectividad OCI via DataLakeProvider ===")

    try:
        provider = DataLakeProvider()
    except ValueError as e:
        logger.error(f"❌ Error al inicializar DataLakeProvider: {e}")
        logger.error("Verificá que OCI_ACCESS_KEY, OCI_SECRET_KEY y OCI_NAMESPACE estén seteados.")
        return False

    # 1. Escribir un archivo de prueba
    df = pd.DataFrame({
        "test_col": ["hello", "world"],
        "number": [1, 2],
    })

    try:
        uri = provider.write_parquet_chunk(
            df=df,
            zone="bronze",
            table_name="_connectivity_test",
            partition_date="2026-01-01",
            chunk_idx=0,
        )
        logger.info(f"✅ ÉXITO — Archivo escrito en: {uri}")
    except Exception as e:
        logger.error(f"❌ FALLÓ la escritura: {e}")
        return False

    # 2. Verificar que el archivo existe listando la partición
    try:
        keys = provider.list_partition_files("bronze", "_connectivity_test", "2026-01-01")
        logger.info(f"✅ Listado OK — Archivos encontrados: {keys}")
    except Exception as e:
        logger.warning(f"⚠️ Listado falló (no crítico): {e}")

    # 3. Leer el archivo de vuelta
    try:
        df_back = provider.read_parquet_partition("bronze", "_connectivity_test", "2026-01-01")
        logger.info(f"✅ Lectura OK — {len(df_back)} filas leídas:\n{df_back.to_string()}")
    except Exception as e:
        logger.warning(f"⚠️ Lectura falló: {e}")

    return True

if __name__ == "__main__":
    ok = test_oci()
    sys.exit(0 if ok else 1)
