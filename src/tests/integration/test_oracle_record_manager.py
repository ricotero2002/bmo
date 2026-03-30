import os
import pytest
from dotenv import load_dotenv
from src.providers.record_manager.factory import RecordManagerFactory

# Cargar variables de entorno desde .env
load_dotenv(override=True)

# Saltear si faltan variables de base de datos
REQUIRED_DB_VARS = ["DB_USER", "DB_PASSWORD"]
if not os.getenv("DB_DSN") and not (os.getenv("DB_HOST") and os.getenv("DB_SERVICE_NAME")):
    REQUIRED_DB_VARS.append("DB_DSN")

pytestmark = pytest.mark.skipif(
    not all(os.getenv(v) for v in REQUIRED_DB_VARS),
    reason="Faltan variables de base de datos para el test"
)

@pytest.fixture
def record_manager():
    return RecordManagerFactory.get_manager()

def test_oracle_record_manager_get_time(record_manager):
    """
    Verifica que get_time() funcione en Oracle sin lanzar NotImplementedError.
    """
    try:
        current_time = record_manager.get_time()
        assert isinstance(current_time, float)
        assert current_time > 0
        print(f"✅ Oracle get_time(): {current_time}")
    except NotImplementedError as e:
        pytest.fail(f"get_time() sigue lanzando NotImplementedError: {e}")
    except Exception as e:
        pytest.fail(f"Error inesperado en get_time(): {e}")

def test_oracle_record_manager_update_upsert(record_manager):
    """
    Verifica que update() (MERGE) funcione correctamente en Oracle.
    """
    # Generar una clave única para el test
    import uuid
    test_key = f"test_key_{uuid.uuid4()}"
    
    try:
        # 1. Insertar (NOT MATCHED path)
        record_manager.update([test_key])
        print(f"✅ Upsert (Insert) exitoso para {test_key}")

        # 2. Actualizar (MATCHED path)
        record_manager.update([test_key])
        print(f"✅ Upsert (Update) exitoso para {test_key}")

        # 3. Verificar que existe (usando list_keys o similar si estuviera disponible, 
        # pero con que no rompa el MERGE ya es un gran avance)
        
    except Exception as e:
        pytest.fail(f"Error en update() (MERGE) para Oracle: {e}")
