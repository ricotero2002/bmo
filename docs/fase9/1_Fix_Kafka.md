# Fase 9 - Fix de Kafka SSL (Legacy Provider)

## Estado

Implementacion iniciada. El objetivo de esta entrega es estabilizar la publicacion y consumo Kafka contra Aiven en OKE corrigiendo la carga del legacy provider de OpenSSL en runtime.

## Problema

En produccion, el productor Kafka fallaba con errores similares a:

- `Failed to load OpenSSL provider "legacy"`
- `could not load the shared library ... legacy.so`
- fallos de handshake SASL_SSL con Aiven Kafka

## Cambios realizados

### Runtime

- Se agrego `src/providers/messaging/openssl_runtime.py` para detectar y configurar `OPENSSL_CONF` y `OPENSSL_MODULES` antes de inicializar `confluent-kafka`.
- Se agrego `docker/openssl/openssl.cnf` con carga explicita de `default` y `legacy` providers.

### Imagen Docker

- Se actualizo `docker/Dockerfile` para instalar `openssl`, copiar la configuracion de providers y exportar variables de entorno OpenSSL en las imagenes `base-final` y `local`.

### Kafka

- `src/providers/messaging/kafka_config.py` ahora valida credenciales SASL en produccion y falla rapido si faltan.
- Se agrego soporte de debug controlado via `KAFKA_SSL_DEBUG`.
- `src/providers/messaging/kafka_producer.py` y `src/workers/kafka_consumer.py` inicializan el runtime OpenSSL antes de importar `confluent_kafka`.

### Kubernetes OKE

- Se propagaron `OPENSSL_CONF`, `OPENSSL_MODULES` y `KAFKA_SSL_PROVIDER` en:
  - `k8s/prod/apps-deployment.yaml`
  - `k8s/prod/kafka-deployment.yaml`
- Se agregaron `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_SASL_USERNAME` y `KAFKA_SASL_PASSWORD` donde corresponde.

### Tests

- Se agrego `src/tests/unit/test_kafka_runtime.py` para validar la config Kafka de produccion y la configuracion del runtime OpenSSL.

## Validacion esperada

1. Construir la imagen de produccion.
2. Levantar los pods en OKE.
3. Confirmar que no aparecen errores de `legacy.so` en logs.
4. Ejecutar un envio de prueba con `save_note_to_knowledge_base`.
5. Verificar que el mensaje llega al consumer y se procesa sin errores SSL.

## Siguientes pasos

- Ejecutar el rollout canary de Kafka consumer y API.
- Monitorear logs de handshake y producer initialization.
- Si el fix es estable, continuar con los siguientes tracks de Fase 9 (Lakehouse, ELT, LLMOps, BI).