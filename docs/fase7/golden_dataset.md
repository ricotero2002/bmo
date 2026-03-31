3. Documentos de Prueba y Golden Dataset
Aquí tienes tres textos simulados con diferentes tipologías para probar la extracción de contexto, junto con preguntas y respuestas esperadas para evaluar tu RAG.

Documento 1: Notas de Reunión (meeting_notes_daily_14_03.md)
Fecha: 14 de Marzo de 2026
Participantes: Abril, Martín, Sofía.
Tema: Sincronización del proyecto de Asistente Personal.

Notas:
Abril comentó que la integración con LangGraph está funcionando bien, pero estamos teniendo problemas de memoria cuando el historial del RAG se hace muy largo. Propuso truncar los mensajes de las herramientas para no sobrepasar el límite de tokens de Oracle. Martín va a revisar el clúster de Kubernetes porque ayer tuvimos un pico de latencia en los workers de Celery al procesar PDFs grandes.

Action Items:

Implementar un nodo de limpieza de memoria en el grafo (Abril).

Escalar los pods de Celery en K8s a un mínimo de 3 réplicas (Martín).

Revisar la configuración de los topics de Kafka para los eventos de ingesta.

Pregunta Golden: ¿Qué tarea se le asignó a Martín en la reunión del 14 de marzo y por qué?

Respuesta Golden: A Martín se le asignó escalar los pods de Celery en Kubernetes a un mínimo de 3 réplicas, y revisar el clúster porque el día anterior hubo un pico de latencia al procesar PDFs grandes.

Documento 2: Notas de Estudio (clase_sistemas_distribuidos.txt)
Materia: Sistemas Distribuidos Avanzados
Unidad 4: Procesamiento de flujos de datos (Stream Processing).

Kafka es una plataforma de streaming distribuida que nos permite publicar y suscribirnos a flujos de registros. A diferencia de las colas de mensajes tradicionales, Kafka retiene los mensajes durante un tiempo configurable (incluso si ya fueron leídos) y basa su rendimiento en el uso eficiente del page cache del sistema operativo y lecturas/escrituras secuenciales en disco.
Apache Spark, por otro lado, puede consumir datos de Kafka usando Spark Streaming. Spark procesa los datos en micro-lotes (micro-batches), lo que ofrece tolerancia a fallos mediante RDDs, aunque introduce una latencia ligeramente mayor comparado con sistemas de streaming puro como Flink.

Pregunta Golden: ¿Cuál es la principal diferencia mencionada entre cómo Kafka maneja los mensajes y una cola de mensajes tradicional?

Respuesta Golden: La principal diferencia es que Kafka retiene los mensajes durante un tiempo configurable, incluso después de haber sido leídos, mientras que las colas tradicionales suelen eliminarlos una vez consumidos.

Documento 3: Ideas y To-Dos (ideas_proyecto_tesis.md)
Contexto: Lluvia de ideas para la arquitectura de la tesis.

El objetivo principal de la plataforma es tener módulos separados para alumnos y profesores.
Para el backend, estoy dudando entre usar FastAPI (con Python) o Spring Boot (con Java). FastAPI me permitiría integrar los modelos de Machine Learning mucho más fácil y armar prototipos rápidos. Sin embargo, Spring Boot tiene un ecosistema más robusto para patrones empresariales.

Pendientes:

Armar un cuadro comparativo de rendimiento entre FastAPI y Spring Boot conectándose a una base de datos Neo4j.

Investigar cómo usar Redis para cachear las respuestas frecuentes del módulo de alumnos.

Pregunta Golden: ¿Qué tecnología se está considerando para cachear respuestas en el módulo de alumnos de la plataforma?

Respuesta Golden: Se está considerando utilizar Redis para cachear las respuestas frecuentes del módulo de alumnos.