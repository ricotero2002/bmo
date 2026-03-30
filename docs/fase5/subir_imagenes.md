2. Script/Comandos para compilar y subir manualmente la imagen (ARM64)
Para compilar tu imagen específicamente para tus nodos gratuitos Ampere A1 (arquitectura ARM) y subirla a Oracle, abre tu terminal en la carpeta donde está tu archivo Dockerfile y ejecuta estos comandos.

Paso A: Iniciar sesión en el registro de Oracle (OCIR)

Bash
docker login <region>.ocir.io
Username: Deberás ingresar tu espacio de nombres y usuario en el formato <tu-namespace>/<tu-correo>. Si usas un proveedor de identidad, el formato suele ser <tu-namespace>/oracleidentitycloudservice/<tu-correo>.

Password: Pega aquí el Auth Token que generaste previamente en la consola de Oracle.

Paso B: Compilar y subir la imagen multi-arquitectura
Utiliza el comando buildx para forzar la compilación en arquitectura ARM, etiquetar la imagen y empujarla al registro en una sola línea:

Bash
docker buildx build --platform linux/arm64 --target final-api -f docker/Dockerfile -t <region>.ocir.io/<tenancy>/personal_ai_api:latest --push.

docker buildx build --platform linux/arm64 --target final-worker -f docker/Dockerfile -t <region>.ocir.io/<tenancy>/personal_ai_worker:latest --push.

(Nota: Asegúrate de reemplazar los datos entre los símbolos < > con tu información real y de no olvidar el punto . al final del comando, ya que le indica a Docker que el contexto de construcción es la carpeta actual).

3. ¿Dónde chequear que se subió correctamente?
Para verificar de manera visual que tu imagen ya está alojada de forma segura en Oracle Cloud:

Abre el menú principal de navegación (hamburguesa) en la parte superior izquierda de tu consola de OCI.

Desplázate hacia Developer Services (Servicios para desarrolladores).

Haz clic en Container Registry (Registro de contenedores).

Selecciona el compartimento donde estás trabajando y asegúrate de estar en la región correcta.

Allí verás una lista con tus repositorios. Al hacer clic en el nombre de tu repositorio, verás la imagen etiquetada como latest y podrás confirmar que figura bajo la arquitectura arm64 o aarch64, lo que significa que tus nodos gratuitos la podrán ejecutar sin problemas.

