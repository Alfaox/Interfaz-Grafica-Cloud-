# Publicar AgroKODIT en PythonAnywhere, paso a paso

Primera publicación educativa con SQLite y datos ficticios. El proyecto local sigue funcionando como antes. Crear la cuenta y subir el ZIP no publica automáticamente la aplicación; la publicación ocurre al configurar la aplicación Web y recargarla.

## 1. Subir el código

En tu Mac, el archivo preparado es `publicacion/agrokodit-pythonanywhere.zip`.

En PythonAnywhere abre **Files**, vuelve a tu carpeta personal `/home/TU_USUARIO` y usa **Upload a file** para subir ese ZIP. El paquete contiene una carpeta `agrokodit`, por lo que no debes crear otra carpeta con ese nombre para descomprimirlo.

Abre **Consoles → Bash** y ejecuta:

```bash
cd ~
unzip agrokodit-pythonanywhere.zip
ls ~/agrokodit
```

Debes ver `manage.py`, `requirements.txt`, `core` y `config`. Si ya existe una instalación anterior, detente antes de descomprimir y prepara una actualización con respaldo; estos pasos describen una primera instalación.

## 2. Elegir Python y crear el entorno

Lista las versiones que tiene tu cuenta:

```bash
ls /usr/bin/python3.*
```

Elige Python 3.13 si está disponible. Si no, usa otra versión instalada entre 3.10 y 3.14. La aplicación Web debe usar exactamente la misma versión que este entorno. En el ejemplo usamos 3.13:

```bash
cd ~/agrokodit
mkvirtualenv agrokodit-env --python=/usr/bin/python3.13
python -m pip install -r requirements.txt
```

Esto instala Django y sus dependencias en el servidor; no se sube `.venv` desde el Mac. Cuando vuelvas a una consola nueva, activa el entorno con `workon agrokodit-env`.

## 3. Configurar el dominio y los secretos

Usa el dominio exacto asignado a tu cuenta, sin `https://` ni una barra final. Reemplaza `TU_USUARIO`:

```bash
python scripts/configurar_pythonanywhere.py --host TU_USUARIO.pythonanywhere.com
export DJANGO_SETTINGS_MODULE=config.settings_pythonanywhere
```

En cuentas de la región europea el dominio puede terminar en `.pythonanywhere.eu`; copia el que muestre tu cuenta. El programa genera una clave aleatoria y la guarda en `~/.agrokodit-produccion.json`, fuera del código, con permisos privados. Nunca debes copiar su contenido al chat ni al ZIP. Volver a ejecutar el programa con el mismo dominio conserva la clave.

La variable `DJANGO_SETTINGS_MODULE` indica a Django qué configuración debe usar. El entorno local utiliza `config.settings`; el sitio público utiliza `config.settings_pythonanywhere`, con DEBUG deshabilitado, dominio específico, cookies seguras y HTTPS.

En cada consola nueva, vuelve a ejecutar el `export` después de activar el entorno. El archivo WSGI también fija esta configuración para las visitas web; exportarlo en la consola por sí solo no configura los trabajadores Web.

## 4. Crear tablas y archivos estáticos

Con el entorno activo y la variable anterior exportada:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

`migrate` crea una base nueva en el servidor; no utiliza la base de datos de tu Mac. `collectstatic` reúne CSS y JavaScript en `~/agrokodit/staticfiles`. Los avisos de HSTS sobre subdominios/preload pueden aparecer: no se activan estas políticas para todos los dominios de PythonAnywhere, ya que no son nuestros. Revisa cualquier otro aviso antes de publicar.

## 5. Elegir cuentas y datos de presentación

Para mostrar las pantallas con datos ficticios:

```bash
python manage.py seed_operacion_demo --ask-password
```

La consola pedirá una contraseña nueva de al menos 14 caracteres y su confirmación. Al escribirla no verás letras ni asteriscos; es normal. No la pongas en comandos ni la compartas en el chat. Las cuentas que se creen (`admin`, `jefe`, `trabajador`, etc.) usarán esa clave. Se conservan las claves de cuentas que ya existan.

En esta configuración, el comando exige la opción interactiva para evitar publicar cuentas con la contraseña demo conocida. No ejecutes `seed_demo` con sus valores por defecto en el sitio público.

Si prefieres una base vacía, omite la carga demo y crea una cuenta administrativa interactivamente:

```bash
python manage.py createsuperuser
```

El usuario creado será Administrador en AgroKODIT. Usa la página de Usuarios para agregar jefes y trabajadores más adelante.

## 6. Crear la aplicación Web

Abre **Web → Add a new web app**, elige el dominio gratuito y selecciona **Manual configuration**. No elijas la opción para generar un nuevo proyecto Django: el proyecto ya existe. Selecciona la misma versión de Python que utilizaste al crear el entorno.

Completa:

- **Source code:** `/home/TU_USUARIO/agrokodit`
- **Working directory:** `/home/TU_USUARIO/agrokodit`
- **Virtualenv:** `/home/TU_USUARIO/.virtualenvs/agrokodit-env`

En **Code**, abre el enlace **WSGI configuration file**. Es el archivo de `/var/www/..._wsgi.py` que crea PythonAnywhere; no `config/wsgi.py` del proyecto. Sustituye su contenido por el del archivo `deploy/pythonanywhere_wsgi.py` incluido en el ZIP. Ese código detecta tu carpeta personal y arranca la configuración de publicación.

## 7. Conectar el diseño y habilitar HTTPS

En **Web → Static files**, agrega:

| URL | Directory |
| --- | --- |
| `/static/` | `/home/TU_USUARIO/agrokodit/staticfiles` |

Guarda la entrada. En la sección de seguridad activa **Force HTTPS**, si aparece. El dominio gratuito ya cuenta con certificado del proveedor; no necesitas comprar un dominio o certificado para esta demostración.

Pulsa **Reload**. Abre `https://TU_USUARIO.pythonanywhere.com` y comprueba:

1. Aparece el formulario de acceso con su diseño.
2. Puedes iniciar sesión con la cuenta creada y su nueva contraseña.
3. Reportes, asistencia y cuadrillas cargan correctamente.
4. Cerrar sesión vuelve a la pantalla de acceso.
5. En el celular se abre el menú y los formularios son utilizables.

Si algo falla, revisa el **Error log** de la pestaña Web. Comparte solo el mensaje del error, nunca contraseñas, tokens ni el archivo privado de configuración.

## Qué no hacemos en esta primera publicación

Todavía no se migra a MySQL ni se implementan procedimientos almacenados. SQLite y la cuenta gratuita son para una demostración de bajo tráfico; las pruebas locales no garantizan capacidad en este alojamiento. La cuenta gratuita puede requerir renovación manual según lo que indique tu panel. Los datos demo son ficticios; no cargues información de trabajadores reales durante la prueba.

Antes de futuras actualizaciones, guarda una copia de `db.sqlite3` y conserva de forma privada `.agrokodit-produccion.json`. No reemplaces la base con una copia local al actualizar código. Cambiar o perder la clave privada invalida las sesiones existentes.

## Referencias oficiales

- [Desplegar un proyecto Django existente](https://help.pythonanywhere.com/pages/DeployExistingDjangoProject/).
- [Subir archivos ZIP](https://help.pythonanywhere.com/pages/UploadingAndDownloadingFiles/).
- [Configurar archivos estáticos](https://help.pythonanywhere.com/pages/DjangoStaticFiles/).
- [HTTPS en PythonAnywhere](https://help.pythonanywhere.com/pages/HTTPSSetup/).
