Notas de Reunión 14 de Marzo de 2026
falta una semana para terminar la iteracion

hay varios problemas con la sincronizacion de los ditintos servicios cloud.

Abril comentó que la integración con LangGraph está funcionando bien, pero estamos teniendo problemas de memoria cuando el historial del RAG se hace muy largo.
Ella dijo que se va a encargar de la limpieza.
Ademas ella propuso truncar los mensajes de las herramientas para no sobrepasar el límite de tokens de Oracle.

Martín va a revisar el clúster de Kubernetes porque ayer tuvimos un pico de latencia en los workers de Celery al procesar PDFs grandes, capas el problema tiene que ver con celery o con kafka.
El se va a encagar de chequear celery.

Yo deberia revisar la configuración de los topics de Kafka para los eventos de ingesta.

Tenemos que trabajar rapido y mostrar avances en 2 o 3 dias para poder conminicarnos mejor con el team encargado del frontend ya que no pueden probar tanto sin estos servicios.