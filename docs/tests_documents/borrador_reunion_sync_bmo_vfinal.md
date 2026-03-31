Reunión del 26 de marzo de 2026
Partiparon Abril, Marcos y Yo (por Discord)
Sincronización general del proyecto del Asistente (BMO), infraestructura y facultad.


Bueno, arrancamos la llamada a las 18hs. Marcos me decía que Kafka es un overkill total para un proyecto personal, pero le expliqué que la idea de la Fase 3 es probar la ingesta masiva de documentos y si le tiro 100 PDFs de una a Celery sin un broker en el medio, se me va a colgar todo el clúster local de K3d. Ah, hablando de eso, ayer Oracle Cloud me mató el nodo Always Free (Ampere A1) por quedarme sin memoria. Tengo que acordarme SÍ O SÍ de bajarle los resource limits al pod de PostgreSQL y al de MinIO en los manifests de Kubernetes.

Cambiando de tema, Abril probó el bot hoy a la mañana para buscar unas notas viejas y me dijo que tardó como 15 segundos en responder. Me parece que el problema está en el grafo de LangGraph. El nodo de grade_documents está haciendo demasiados reintentos cuando Pinecone no devuelve nada bueno. Capaz tengo que cambiar el LLM de evaluación por uno más rápido (Flash) o meter el Re-Ranker de Cohere que estuvimos hablando, aunque tengo que revisar si el free-tier de Cohere me banca esa cantidad de requests.

Anotación mental: ir al supermercado a comprar café y balanceado para el perro, no queda nada. Y pagar la tarjeta antes del 10.

Volviendo al código. El orchestrator.py está fallando cuando un documento no tiene texto. Tiró un error 500 porque intentó hacer el hash de un content que venía en None. Hay que meter un if not content: return error al principio.
Además, tengo que meter lo del Enum estricto en el Pydantic para el doc_type (meeting_notes, general, etc.) así el LLM no alucina categorías cuando hace el pre-chunking. La idea de poner el global_summary al principio de cada chunk me parece brillante, lo voy a implementar este finde.


Che, ¿cómo hacíamos para que el retriever entienda si quiero buscar algo del año pasado? Ah, cierto, el parámetro custom_date en la task de Celery. Tengo que modificar el frontend para que mande la fecha de creación original del archivo y no la fecha en la que lo estoy subiendo. Si no, cuando suba mis apuntes de Sistemas Distribuidos de 2025, el asistente va a pensar que los escribí hoy.

Tareas sueltas que quedaron (hacer antes del domingo):

Revisar por qué el MarkItDown falla con algunos PDFs escaneados (capaz falta OCR).

Implementar el borrado de memoria temporal en LangGraph para los ToolMessage pesados.

Mandarle el borrador del texto de aniversario a Abril (ya pasó un año, qué locura).

Ver si paso los workers de Celery a RabbitMQ si Kafka me sigue consumiendo tanta RAM en el clúster de OKE.

Fin de la llamada a las 19:30. Se cortó la luz 5 minutos, revisar los logs de Redis por las dudas a ver si persistió bien la sesión del chat.