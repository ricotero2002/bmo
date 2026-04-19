import pytest


@pytest.fixture(autouse=True)
def clear_openssl_cache():
    from src.providers.messaging.openssl_runtime import configure_openssl_runtime

    configure_openssl_runtime.cache_clear()
    yield
    configure_openssl_runtime.cache_clear()


def test_build_kafka_conf_production_uses_tls_and_sasl(tmp_path, monkeypatch):
    from src.providers.messaging.kafka_config import build_kafka_conf

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.example.com:9093")
    monkeypatch.setenv("KAFKA_SASL_USERNAME", "avnadmin")
    monkeypatch.setenv("KAFKA_SASL_PASSWORD", "super-secret")
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("dummy-ca")
    monkeypatch.setenv("KAFKA_SSL_CA_LOCATION", str(ca_file))

    conf = build_kafka_conf()

    assert conf["bootstrap.servers"] == "kafka.example.com:9093"
    assert conf["security.protocol"] == "SASL_SSL"
    assert conf["sasl.mechanisms"] == "SCRAM-SHA-256"
    assert conf["sasl.username"] == "avnadmin"
    assert conf["sasl.password"] == "super-secret"
    assert conf["ssl.ca.location"] == str(ca_file)


def test_build_kafka_conf_requires_production_credentials(monkeypatch):
    from src.providers.messaging.kafka_config import build_kafka_conf

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("KAFKA_SASL_USERNAME", raising=False)
    monkeypatch.delenv("KAFKA_SASL_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="KAFKA_SASL_USERNAME"):
        build_kafka_conf()


def test_configure_openssl_runtime_uses_explicit_env(tmp_path, monkeypatch):
    from src.providers.messaging.openssl_runtime import configure_openssl_runtime

    conf_file = tmp_path / "openssl.cnf"
    conf_file.write_text("openssl_conf = openssl_init")
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir()
    (modules_dir / "legacy.so").write_text("dummy")

    monkeypatch.setenv("OPENSSL_CONF", str(conf_file))
    monkeypatch.setenv("OPENSSL_MODULES", str(modules_dir))

    result = configure_openssl_runtime()

    assert result["openssl_conf"] == str(conf_file)
    assert result["openssl_modules"] == str(modules_dir)
    assert result["kafka_ssl_provider"] == "legacy"