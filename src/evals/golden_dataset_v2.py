# Golden Dataset V2 for RAG & Agentic Chunking Evaluation

GOLDEN_DATASET = [
    {
        "name": "Test 1: Brainstorming & Architecture",
        "category": "brainstorming",
        "raw_text": (
            "Borrador de ideas de la madrugada. Estuve pensando seriamente en la migración de BMO. "
            "OKE me tiene cansado con las caídas de los nodos por falta de memoria, capaz me conviene armar un clúster de EKS en AWS aprovechando unos créditos que me dieron, o levantar EC2 directamente con K3s. "
            "El tema de los secretos lo quiero manejar sí o sí con Infisical, basta de andar pasando los .env hardcodeados o por chat. "
            "Por otro lado, estuve revisando los logs y la lógica de ruteo del agente está muy lenta. En vez de usar un solo LLM gigante para todo, voy a implementar una lógica de ruteo donde un modelo chiquito y rápido (tipo Haiku) solo clasifique la complejidad de la query, y en base a eso elija a qué agente o modelo pesado llamar. Ahorro latencia y plata. "
            "Che, me crucé con un artículo de GraphRAG y me voló la cabeza, pero creo que para las búsquedas de BMO, con sacar las relaciones directamente de la base de datos sin forzar a que sea específico con los schemas de Pydantic ya me alcanza, la otra vez falló todo por intentar tiparlo tan fuerte. "
            "Acordarme de decirle a Abril si quiere ir a merendar al centro mañana por nuestro aniversario. "
            "Ah, y sobre la facultad: para la presentación final de OOPingo tengo que armar bien el diagrama de la base de datos de Spring Boot, sobre todo la tabla donde guardo las mecánicas de gamificación que quedó medio confusa de explicar."
        ),
        "ideal_chunks": [
            "Para la migración del asistente, estoy evaluando dejar Oracle Kubernetes Engine (OKE) por sus caídas de memoria y armar un clúster de EKS en AWS o usar instancias EC2 con K3s. Además, gestionaré los secretos del entorno utilizando Infisical para evitar archivos .env hardcodeados.",
            "Para optimizar la latencia y los costos del agente, implementaré un modelo pequeño que clasifique la complejidad de la consulta y decida a qué modelo pesado enrutarla. Respecto a GraphRAG, la estrategia de recuperación sacará las relaciones directamente de la base de datos en lugar de usar esquemas estrictos de Pydantic, ya que esto último causó fallos anteriores.",
            "Debo recordar invitar a Abril a merendar al centro mañana por nuestro aniversario.",
            "Para la presentación final de la tesis de OOPingo, debo mejorar el diagrama de la base de datos de Spring Boot, haciendo foco en aclarar la estructura de la tabla de mecánicas de gamificación."
        ],
        "eval_query": "¿Cómo decidiste optimizar la lógica de ruteo del agente para bajar la latencia?",
        "expected_answer": "Decidiste optimizar la latencia y los costos usando un modelo pequeño (como Haiku) para clasificar primero la complejidad de la consulta del usuario, y usar esa clasificación para enrutar la petición al modelo o agente pesado correspondiente."
    },
    {
        "name": "Test 2: Meeting Notes & Docker Troubleshooting",
        "category": "meeting_notes",
        "raw_text": (
            "Llamada por Discord para preparar las entrevistas. La semana que viene tengo las entrevistas técnicas con Amperity y Siemens para el puesto de AI Engineer, y también mandé el CV a NEC. "
            "Les mostré a los chicos el speech que armé. Me recomendaron hacer muchísimo foco en AI Safety, privacidad de datos y ética, porque a las empresas grandes les importa un montón que no filtres datos de usuarios. "
            "Voy a sumar un slide a la presentación explicando cómo podemos implementar NeMo Guardrails y el enmascaramiento de PII en los pipelines de ingesta. "
            "En el medio de la charla quise levantar el entorno y se me crasheó el Docker Compose local; parece que el contenedor de RabbitMQ se quedó sin espacio en el volumen de Docker y arrastró a todos los workers de Celery a la muerte. "
            "Tengo que purgar los volúmenes con un `docker system prune` o subirle el límite al disco virtual hoy a la noche sin falta. "
            "Nada que ver, pero le tengo que transferir la mitad de las expensas al dueño del depto antes del viernes, siempre me olvido de eso."
        ),
        "ideal_chunks": [
            "La próxima semana tengo entrevistas técnicas para el puesto de AI Engineer en Amperity y Siemens, y envié mi CV a NEC. En mi presentación haré un fuerte enfoque en AI Safety, ética y privacidad de datos, agregando una diapositiva sobre la implementación de NeMo Guardrails y el enmascaramiento de PII (Información de Identificación Personal) en los pipelines.",
            "El entorno local de Docker Compose crasheó porque el volumen del contenedor de RabbitMQ se quedó sin espacio, lo que provocó la caída de los workers de Celery. Debo solucionar esto purgando los volúmenes con 'docker system prune' o aumentando el límite del disco virtual.",
            "Debo transferir la mitad de las expensas al dueño del departamento antes del viernes."
        ],
        "eval_query": "Tengo una entrevista con Siemens pronto, ¿qué herramientas específicas iba a mencionar en la presentación para demostrar conocimientos en privacidad y AI Safety?",
        "expected_answer": "Para demostrar conocimientos en AI Safety y privacidad en la entrevista, ibas a mencionar la implementación de NeMo Guardrails y técnicas de enmascaramiento de PII en los pipelines de ingesta."
    },
    {
        "name": "Test 3: Post-Mortem & Kafka Theory",
        "category": "troubleshooting",
        "raw_text": (
            "Post-mortem del problema de la Fase 3. Ayer intenté hacer la prueba de ingesta masiva de documentos y falló todo el pipeline. "
            "Los logs tiraban que MinIO estaba rechazando las conexiones que venían del broker. "
            "Empecé a revisar y el problema era que el consumidor asíncrono no estaba haciendo bien el commit de los offsets de los mensajes y se terminó generando un cuello de botella enorme en la persistencia. "
            "Lo solucioné temporalmente subiéndole el timeout al worker. "
            "Mientras debuggeaba esto, estaba escuchando de fondo una clase grabada sobre arquitecturas distribuidas. "
            "El profesor explicaba que usar un sistema como Apache Kafka está buenísimo para sistemas reactivos por su arquitectura de append-only log, pero que si no configurás bien la 'retention policy', te comés el disco entero del servidor en un par de días. Literalmente lo que me estuvo pasando a mí en el clúster. \n"
            "Tareas que me quedan para este fin de semana:\n"
            "- Ajustar la política de retención de los topics a 24 horas.\n"
            "- Terminar de redactar el informe final de OOPingo.\n"
            "- Comprar las entradas para el cine para ir con mi novia.\n"
            "- Migrar el tracking de estado de las ingestas de SQLite a Postgres para que se banque mejor la concurrencia de los workers."
        ),
        "ideal_chunks": [
            "Durante la prueba de ingesta masiva de la Fase 3, el pipeline falló porque MinIO rechazaba conexiones. El error se originó debido a que el consumidor asíncrono no realizaba correctamente el commit de los offsets, causando un cuello de botella en la persistencia. La solución temporal fue aumentar el timeout del worker.",
            "En sistemas reactivos, la arquitectura append-only log de Apache Kafka es muy útil, pero es crítico configurar correctamente la política de retención (retention policy) para evitar agotar el almacenamiento del disco del servidor rápidamente.",
            "Tareas pendientes para el fin de semana: 1) Ajustar la política de retención de los topics a 24 horas. 2) Terminar de redactar el informe final de la tesis OOPingo. 3) Comprar entradas para el cine para ir con mi novia. 4) Migrar la base de datos de tracking de ingestas de SQLite a Postgres para soportar mayor concurrencia."
        ],
        "eval_query": "¿Qué bases de datos voy a usar para resolver el problema de concurrencia en el tracking de las ingestas masivas?",
        "expected_answer": "Vas a migrar el tracking del estado de las ingestas desde SQLite hacia PostgreSQL para que pueda soportar de forma robusta la concurrencia de los workers."
    },
    {
        "name": "Doc A: Notas de Reuniones DevOps (K8s) - Desorganizado",
        "category": "meeting_notes",
        "raw_text": (
            "--- Fragmento 1: Reunión Café (02/04/2026) ---\n"
            "Che, con los pibes de Infra estuvimos viendo que Oracle OKE nos está matando el presupuesto. Decidimos pasar todo a EKS o capaz algo más barato si encontramos. "
            "Ah, y el tema de los backups en OCI no está funcionando bien. \n"
            "--- Fragmento 2: Daily con DevOps (05/04/2026) ---\n"
            "Urgente: El cluster explotó. Los workers de Celery tiraron OOM y después vimos un error de KEDA. "
            "Específicamente KEDA v2.12.0 tiene un mambo con SASL_SSL y Kafka en Aiven cuando hay muchos mensajes. "
            "El log decía 'Authentication failed during SASL handshake'. "
            "Estamos usando el broker de Aiven. \n"
            "--- Fragmento 3: Notas sueltas en Notion (07/04/2026) ---\n"
            "Tareas que no me tengo que olvidar:\n"
            "- Rotar secretos de Infisical (vi que algunos vencen).\n"
            "- Ver si KEDA v2.13 o superior arregla el crash de SASL.\n"
            "- Implementar Postgres checkpointer para LangGraph (urgente para persistencia).\n"
            "Me dijo Juan que la migración a Oracle OKE fue un error por los costos de los Load Balancers, mejor volver a AWS."
        ),
        "ideal_chunks": [
            "Notas de reuniones DevOps: El 02/04/2026 se decidió migrar de Oracle OKE a AWS EKS u otra opción más económica debido a los altos costos de infraestructura y problemas con backups en OCI.",
            "Incidente (05/04/2026): Los workers de Celery fallaron por OOM y errores críticos en KEDA v2.12.0 al gestionar la autenticación SASL_SSL con Kafka en Aiven bajo alta carga.",
            "Tareas pendientes (07/04/2026): 1) Rotar secretos en Infisical. 2) Investigar si versiones superiores de KEDA solucionan el bug de SASL. 3) Implementar PostgreSQL checkpointer para la persistencia de LangGraph. Se reafirma la intención de volver a AWS."
        ],
        "eval_query": "En mis notas de la reunión de DevOps se mencionó un error con KEDA. Búscame en la web cuál es la última versión de KEDA y comparala con la versión que anoté que usamos.",
        "expected_answer": "Anotaste que estás utilizando KEDA v2.12.0, el cual presentó un error con la autenticación SASL_SSL de Kafka en Aiven. Según la búsqueda web, la última versión de KEDA es la [X.Y.Z]. Deberías actualizar desde la v2.12.0 a esta nueva versión para verificar si el bug de autenticación fue resuelto."
    },
    {
        "name": "Doc B: Arquitectura Avanzada de LangGraph (Largo)",
        "category": "technical_doc",
        "raw_text": (
            "ESPECIFICACIÓN TÉCNICA: MOTOR DE AGENTES BMO CON LANGGRAPH\n\n"
            "Introducción:\n"
            "El sistema BMO evoluciona hacia una arquitectura de grafos de estado utilizando LangGraph. "
            "Esta transición permite manejar flujos cíclicos, correcciones automáticas y una gestión de memoria jerárquica.\n\n"
            "Componentes del Grafo:\n"
            "1. Nodo 'Task Planner': Responsable de descomponer la consulta del usuario en pasos ejecutables. Debe considerar el contexto reciente y el resumen global.\n"
            "2. Nodo 'Agent': El motor LLM principal que ejecuta las herramientas según el plan.\n"
            "3. Nodo 'Auditor': Verifica alucinaciones y cumplimiento de tareas.\n\n"
            "Gestión de Memoria (Hierarchical Memory):\n"
            "Para evitar el desborde de tokens en conversaciones largas, implementamos un sistema de dos niveles. "
            "El nivel 1 resume cada turno (Summarize Run). El nivel 2 consolida estos resúmenes en un Resumen Global cuando el historial supera los 4 turnos humanos.\n"
            "El sistema debe preservar siempre el último trío de mensajes (Input, Output, Run Summary) para mantener la fluidez inmediata.\n\n"
            "Tareas Pendientes de Implementación:\n"
            "- Desarrollar el nodo 'Task Planner' con soporte para `global_summary`.\n"
            "- Integrar `global_summarization` para inyectar contexto a chunks huérfanos.\n"
            "- Solucionar el RecursionLimit en fallos repetidos de búsqueda.\n"
            "- Migrar de SqliteCheckpointer a PostgresCheckpointer para entornos productivos con alta concurrencia."
        ),
        "ideal_chunks": [
            "La arquitectura de BMO usa LangGraph para flujos cíclicos y memoria jerárquica. El grafo incluye nodos como Task Planner, Agent y Auditor para la ejecución y validación de tareas.",
            "Memoria Jerárquica: Se implementa un sistema de dos niveles (Summarize Run y Global Summary) que se activa tras 4 turnos humanos. Se preservan los últimos 3 mensajes para fluidez inmediata.",
            "Pendientes LangGraph: 1) Nodo Task Planner con soporte para global_summary. 2) Inyección de contexto en chunks vía global_summarization. 3) Manejo de RecursionLimit. 4) Migración a PostgresCheckpointer."
        ],
        "eval_query": "Recuperame las notas de las reuniones de DevOps y los requisitos de LangGraph. Hacé un análisis cruzado de qué tareas quedaron pendientes respecto al framework LangGraph en ambos documentos.",
        "expected_answer": "Analizando ambos documentos, las tareas pendientes para LangGraph son: 1) Implementar PostgreSQL checkpointer (mencionado en DevOps y Requisitos). 2) Desarrollar el nodo 'Task Planner' con soporte para global_summary. 3) Integrar 'Global Summarization'. 4) Solucionar problemas de RecursionLimit."
    },
    {
        "name": "Doc C & D: Auditoría Financiera y Legal APIs",
        "category": "financial_legal",
        "raw_text": (
            "INFORME DE AUDITORÍA DE COSTOS CLOUD Y CUMPLIMIENTO LEGAL (MARZO 2026)\n\n"
            "1. Análisis de Facturación AWS:\n"
            "Se detectó un incremento del 20% en los costos de NAT Gateway. "
            "La causa principal es la transferencia de datos entre zonas de disponibilidad no optimizadas. "
            "Acción requerida: Revisar la configuración de VPC Endpoints para S3 y DynamoDB.\n\n"
            "2. Términos de Servicio API (/api/ask/stream):\n"
            "El uso de los endpoints de streaming está sujeto a las siguientes condiciones:\n"
            "- Autenticación obligatoria vía JWT en el header Authorization.\n"
            "- Límite de 50 peticiones concurrentes por usuario (Tier Enterprise).\n"
            "- El contenido generado es propiedad del usuario, pero los logs de auditoría se conservan por 30 días para cumplimiento normativo (GDPR/LGPD).\n\n"
            "3. Planificación de Pagos:\n"
            "Se debe realizar el pago de las expensas y servicios de oficina antes del día 10 de cada mes para evitar recargos."
        ),
        "ideal_chunks": [
            "Auditoría AWS Mar-2026: El costo de NAT Gateway subió un 20% por tráfico inter-zona. Se requiere configurar VPC Endpoints para S3 y DynamoDB para optimizar costos.",
            "Legales API: El endpoint /api/ask/stream requiere JWT, permite 50 peticiones concurrentes en Tier Enterprise y mantiene logs por 30 días para cumplimiento legal (GDPR).",
            "Finanzas: El pago de expensas y servicios de oficina debe realizarse antes del día 10 de cada mes."
        ],
        "eval_query": "En base a las tareas que anoté que debo hacer con LangGraph esta semana, armame una planificación completa por fases considerando los costos mencionados en la auditoría.",
        "expected_answer": "Planificación para LangGraph enfocada en optimización:\nFase 1 (Costos y Persistencia): Configurar VPC Endpoints (AWS) e implementar Postgres checkpointer.\nFase 2 (Arquitectura): Desarrollar el nodo 'Task Planner' y Global Summarizer.\nFase 3 (Estabilidad): Solucionar errores de RecursionLimit y revisar límites de concurrencia de la API."
    }
]
