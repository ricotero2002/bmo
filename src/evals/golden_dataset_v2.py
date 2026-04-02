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
    }
]
