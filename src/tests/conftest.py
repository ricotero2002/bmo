import sys
import asyncio
import pytest
from dotenv import load_dotenv

def pytest_configure(config):
    """
    Configuración global de pytest.
    """
    # Cargar variables de entorno del sistema y de archivos .env
    load_dotenv(override=True)
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
