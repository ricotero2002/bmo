import os
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CONF_PATHS = (
    Path("/app/docker/openssl/openssl.cnf"),
    Path("/etc/ssl/openssl.cnf"),
    Path("/usr/lib/ssl/openssl.cnf"),
)

DEFAULT_MODULE_DIRS = (
    Path("/usr/lib/x86_64-linux-gnu/ossl-modules"),
    Path("/usr/lib/ssl/modules"),
    Path("/usr/lib64/ossl-modules"),
)


def _first_existing_file(paths: tuple[Path, ...]) -> Path | None:
    for candidate in paths:
        if candidate.is_file():
            return candidate
    return None


def _first_existing_module_dir(paths: tuple[Path, ...]) -> Path | None:
    for candidate in paths:
        if (candidate / "legacy.so").is_file():
            return candidate
    return None


@lru_cache(maxsize=1)
def configure_openssl_runtime() -> dict:
    """Prepare OpenSSL env vars so librdkafka can load the legacy provider."""
    conf_path = os.getenv("OPENSSL_CONF")
    module_dir = os.getenv("OPENSSL_MODULES")

    if not conf_path or not Path(conf_path).is_file():
        detected_conf = _first_existing_file(DEFAULT_CONF_PATHS)
        if detected_conf:
            conf_path = str(detected_conf)
            os.environ["OPENSSL_CONF"] = conf_path

    if not module_dir or not Path(module_dir).exists():
        detected_module_dir = _first_existing_module_dir(DEFAULT_MODULE_DIRS)
        if detected_module_dir:
            module_dir = str(detected_module_dir)
            os.environ["OPENSSL_MODULES"] = module_dir

    provider = os.getenv("KAFKA_SSL_PROVIDER", "legacy")
    os.environ.setdefault("KAFKA_SSL_PROVIDER", provider)

    if not conf_path:
        logger.warning("No se pudo detectar OPENSSL_CONF; se usará la configuración por defecto del contenedor.")
    if not module_dir:
        logger.warning("No se pudo detectar OPENSSL_MODULES; legacy provider podría no estar disponible.")

    return {
        "openssl_conf": conf_path,
        "openssl_modules": module_dir,
        "kafka_ssl_provider": provider,
    }