# AgroKODIT · Gestión agrícola

Aplicación Python/Django 5.2 con interfaces responsivas integradas, usuarios y tres roles: Administrador, Jefe de Cuadrilla y Trabajador.

## Ejecutar en macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

En Windows, activa el entorno con `.venv\Scripts\activate`.

Abre http://127.0.0.1:8000. El comando `seed_demo` crea, si no existen, las cuentas `admin`, `jefe` y `trabajador`, con clave de demostración `AgroKODIT2026!`. No cambia las claves de cuentas existentes. Úsalo solamente en desarrollo.

Si el entorno ya estaba instalado, basta con activar `.venv`, ejecutar `migrate` y arrancar `runserver`. Recarga la página con Cmd+Shift+R si el navegador conserva el CSS anterior.

## Interfaces integradas

- Acceso y cambio de contraseña con autenticación real de Django.
- Panel con métricas de producción, gráfico diario, ranking y accesos según el rol.
- Usuarios: creación, búsqueda y edición de datos, roles y estado activo/inactivo. Los cambios se aplican en las sesiones existentes desde su próxima solicitud.
- Predios → huertos → cuarteles, catálogo de cultivos y temporadas, con edición de fichas y protección de relaciones históricas.
- Cuadrillas con jefe y colleras de dos trabajadores distintos y disponibles; edición de nombres, reasignación de jefe y traslado de colleras para nuevas jornadas.
- Apertura de jornadas por el jefe: cuadrilla propia, cuartel, temporada, fecha, horario y labor.
- Asistencia: entrada, salida, atraso, ausencia, cálculo de horas y validación del jefe. Autogestión opcional por jornada: cada trabajador marca su propia entrada/salida de hoy con hora del servidor.
- Pesajes: kilos, calidad y merma con motivo; correcciones antes del cierre.
- Cierre con resumen y confirmación; reapertura excepcional por administrador con motivo.
- Reportes y ranking de colleras y trabajadores con fechas, predio y cuartel. Comparación de dos temporadas por predio y cultivo, con kilos, mermas, variación y evolución acumulada desde el inicio. Exportación CSV filtrada para administrador e impresión desde el navegador.
- Consultas del trabajador limitadas a su asistencia y producción de las colleras en las que participó.
- Auditoría de accesos, denegaciones y operaciones críticas.

Las pantallas usan registros reales de la base de datos. No se insertan pesajes ficticios ni se utiliza el almacenamiento del prototipo `interfaces/`.

## Primer recorrido con una base vacía

1. Entra como `admin` y crea al menos un segundo trabajador en **Usuarios y roles**.
2. En **Predios y temporadas**, crea un predio, un cultivo, un huerto, un cuartel y una temporada que incluya la fecha de trabajo.
3. En **Cuadrillas y colleras**, crea una cuadrilla asignada a `jefe` y forma una collera con dos trabajadores.
4. Cierra sesión. Entra como `jefe`, abre una jornada desde **Mi cuadrilla** y selecciona la ubicación y temporada.
5. En **Asistencia**, registra las marcas; en **Registrar kilos**, ingresa uno o más pesajes.
6. Abre **Reportes y rankings**: los gráficos, totales y ranking reflejan esos pesajes. Ajusta el período si la jornada no es de esta semana.
7. Revisa **Cerrar jornada** y confirma. Las escrituras posteriores serán rechazadas también por el servidor.
8. El administrador puede supervisar las jornadas y reabrirlas con un motivo mientras la temporada siga abierta.

## Arquitectura y seguridad

- `core/models.py`: entidades, claves foráneas protegidas y restricciones relacionales.
- `core/forms.py`: tipos, rangos, fechas y selección de recursos permitidos.
- `core/services.py`: autorización por recurso, transacciones, colleras, apertura/cierre, pesajes y asistencia.
- `core/reporting.py`: consolidaciones y filtros con ORM, aplicados antes de calcular o exportar.
- `core/views.py` y `core/urls.py`: controladores y rutas.
- `core/templates/core/` y `core/static/core/`: presentación y navegación móvil.

Las jornadas guardan el jefe responsable y sus colleras participantes. Desarmar una collera no borra su historial; para cambiar integrantes se crea otra collera. `Participacion.fecha` materializa la fecha de la jornada para imponer la unicidad collera/fecha entre cuadrillas; el servicio de apertura la asigna desde la jornada, nunca desde un campo del navegador.

Los cambios de asistencia y kilos, el cierre y la reapertura comparten bloqueos transaccionales sobre temporada y jornada. Los formularios de escritura requieren CSRF; el acceso por rol y por jefe se verifica en el servidor. Las contraseñas usan Argon2 cuando está instalada la dependencia indicada.

## Base de datos

Por defecto se utiliza SQLite local. Para MySQL/MariaDB instala `mysqlclient` y define `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_HOST` y `MYSQL_PORT`; ejecuta las migraciones sobre esa base. Cambiar el motor no traslada automáticamente los datos de SQLite.

Esta integración de interfaces consulta mediante el ORM. **Todavía no implementa los procedimientos almacenados del Paso 1 de la actividad.** Ese paso requiere preparar y comprobar MySQL/MariaDB. Las pruebas actuales se ejecutaron con SQLite, no validan concurrencia real en MySQL. La migración `0003` añade únicamente una preferencia de autogestión a la jornada; MySQL y los procedimientos almacenados quedan para la etapa final.

## Validación

```bash
python manage.py check
python manage.py test
python manage.py makemigrations --check --dry-run
```

Se prueban permisos por rol y por recurso, pantallas con/sin datos, totales, filtros, exportación, validación de kilos, exclusividad de colleras, cronología de asistencia, CSRF, cierre, reapertura, edición de observaciones, ranking individual y paginación. La carga simultánea se comprueba por separado con el script de rendimiento.

## Alcance pendiente

Esta entrega conecta las interfaces y el flujo operativo. No constituye la implementación completa de las 50 historias del informe. Siguen pendientes, entre otros, exportación XLSX/PDF generada en servidor y procedimientos almacenados. La opción **Imprimir / PDF** usa el diálogo del navegador; la descarga disponible es CSV.

La interfaz se adapta a móvil y utiliza SVG y gráficos CSS locales. Las fuentes web tienen alternativa de sistema. Se requiere revisión visual en navegadores y pruebas de accesibilidad con lector de pantalla.

Antes de publicar configura `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS`, HTTPS, servicio de archivos estáticos y respaldos. No uses las cuentas demo en producción.

## Prototipo anterior

`interfaces/` conserva el prototipo autónomo anterior con datos de ejemplo. La aplicación integrada se abre en **http://127.0.0.1:8000**, no en `interfaces/index.html`.


## Uso de las nuevas funciones

### Usuarios y roles

En **Usuarios y roles → Editar / permisos** puedes corregir datos, cambiar el perfil y desactivar/reactivar una cuenta. No se exponen privilegios internos de Django ni se modifica la contraseña. Para cambiar el rol o desactivar a un trabajador, primero desarma su collera activa. Para hacerlo con un jefe, cierra las jornadas abiertas y reasigna sus cuadrillas a otro jefe. No puedes quitarte el perfil administrador ni desactivar tu propia cuenta; debe conservarse al menos un administrador activo.

### Catálogos

Los botones **Editar** aparecen en Predios y temporadas, en el nuevo listado de cultivos y en las cuadrillas/colleras. El nombre de una collera puede corregirse, pero sus integrantes históricos son inmutables: para cambiarlos, desarma la collera y crea otra. Un huerto con jornadas no puede cambiar de predio; un cuartel con jornadas no puede cambiar de huerto o cultivo. Las fechas de una temporada deben incluir todas sus jornadas. El cambio de jefe requiere cerrar las jornadas abiertas y conserva al responsable original en las jornadas anteriores.

### Traslados

El administrador usa **Cuadrillas y colleras → Trasladar**, selecciona otra cuadrilla y registra el motivo. La collera pasa a la nueva cuadrilla para las jornadas que se abran después del traslado. Las participaciones, asistencias y pesajes ya creados mantienen la cuadrilla y el jefe originales, incluso si su jornada sigue abierta. La misma collera no puede participar en otra cuadrilla en la misma fecha.

### Autogestión de asistencia

Al abrir la jornada, el jefe puede activar **Habilitar autogestión de asistencia**. También puede cambiar esta opción desde **Asistencia → Autogestión de asistencia** mientras la jornada esté abierta. En **Mi asistencia**, el trabajador encuentra **Marcar mi entrada / salida** para la jornada de hoy. La marca usa la hora local del servidor y no acepta una hora ni un trabajador enviados desde el navegador. No permite duplicaciones, marcas ajenas, jornada cerrada, temporada cerrada ni marcas de días anteriores/futuros. Cada marca propia queda pendiente de validación del jefe.

### Comparación de temporadas

En **Reportes y rankings → Comparar temporadas**, elige la referencia y una temporada distinta. Opcionalmente aplica el mismo predio y cultivo a ambas. La vista muestra kilos y mermas registrados, número de jornadas/pesajes, asistencias con entrada, horas completas y variación porcentual. Cuando la referencia tiene cero kilos, no se calcula un porcentaje; se muestra la diferencia absoluta.

La gráfica compara acumulados alineados por días desde el inicio de cada temporada. Son totales registrados, incluyendo jornadas abiertas, no rendimiento por hectárea ni por día; una temporada aún en curso puede tener menos días de trabajo. Un jefe solo compara temporadas y datos de jornadas de las que es responsable. Los trabajadores no tienen acceso a esta vista. La nueva comparación no tiene exportación propia; el CSV existente continúa correspondiendo al reporte de producción filtrado.

## Datos completos de demostración

Para poblar las pantallas en desarrollo:

```bash
python manage.py seed_operacion_demo
```

El comando agrega registros identificados como **DEMO**: dos predios, cuatro huertos/cuarteles, dos cultivos, dos temporadas (anterior cerrada y actual abierta), tres cuadrillas productivas, una cuadrilla de apoyo para probar traslados, seis colleras y trabajadores disponibles. Incluye pesajes de diferentes calidades, mermas, asistencia con atrasos/ausencias y jornadas históricas cerradas. Las tres jornadas de hoy quedan abiertas y con autogestión habilitada; la cuenta `trabajador` puede probar su propia entrada desde cero.

Los datos son ficticios. Los usuarios principales `admin`, `jefe` y `trabajador` conservan sus contraseñas si ya existían. Las cuentas nuevas, como `demo_carolina` y `demo_felipe`, usan por defecto `AgroKODIT2026!`; puedes definir otra clave con `--password`, que se aplica solo a cuentas creadas en esa ejecución.

La carga es transaccional: no borra registros existentes, no reemplaza contraseñas ni completa/modifica jornadas ya registradas. Repetirla el mismo día no duplica datos. Si hay cuentas con perfiles incompatibles o trabajadores ya asignados que impiden formar una collera, la carga se revierte y explica el conflicto. Los registros demo y reales comparten las pantallas y los totales: utiliza estos datos solo en desarrollo.


## Ranking por trabajador

En **Reportes y rankings**, debajo del ranking de colleras aparece el ranking individual. Se calcula con los mismos filtros y permisos. Como los kilos se pesan por collera, se muestra una **estimación matemática de 50 % por integrante**, junto al total de las colleras de esa persona. No mide producción individual real ni ajusta el reparto según asistencia. Los dos integrantes comparten puesto cuando sus acumulados son iguales.

El cálculo utiliza las colleras históricas, incluso si fueron desarmadas o trasladadas; no se usan solamente los equipos activos actuales. Se muestran tres decimales para representar exactamente el reparto de un pesaje de 0,01 kg en dos mitades de 0,005 kg. Los totales generales del reporte continúan sumando cada pesaje una sola vez.

Los pesajes del reporte se muestran en páginas de 50 registros; los totales y rankings incluyen todos los resultados filtrados. La descarga CSV sigue incluyendo todos los pesajes, no solamente la página visible. El CSV existente no incorpora el ranking individual.

## Observaciones posteriores a la apertura

El jefe responsable puede usar **Asistencia → Editar observaciones**, o **Cerrar jornada → Editar observaciones**, para agregar, corregir o borrar el texto (máximo 500 caracteres). El cambio queda auditado y conserva las versiones anterior y nueva en eventos segmentados. Una jornada o temporada cerrada rechaza la edición, también por solicitud directa; primero debe reabrirla un administrador con motivo.

## Rendimiento y concurrencia local

```bash
python scripts/probar_rendimiento.py --workers 8 --requests 80 --extra-pesajes 10000 --output docs/rendimiento_despues.json
```

El script copia SQLite a un directorio temporal. Los usuarios, pesajes adicionales, marcas y cierres de carga se crean solo en esa copia y se eliminan al terminar. Las lecturas usan el cliente interno de Django, con middleware y plantillas; las escrituras llaman a los servicios de dominio desde conexiones independientes. No mide red, navegador ni servidor de producción.

Escenarios: reportes concurrentes; ocho pesajes en una jornada; ocho entradas de trabajadores diferentes; creación simultánea de colleras que compiten por los mismos integrantes; entradas repetidas para un mismo trabajador; cierre simultáneo con ingreso de kilos. Los duplicados de asistencia/colleras deben rechazarse por validación sin errores de base de datos.

Las primeras pruebas detectaron `database is locked` con el modo diferido de SQLite. La configuración local ahora usa `transaction_mode=IMMEDIATE` y espera de 20 segundos para serializar escrituras desde el inicio de la transacción. Esto no agrega bloqueos por fila ni transforma SQLite en una base para alta concurrencia. Se requiere Django 5.2 o superior dentro de la rama 5.x, que ya utiliza el proyecto. MySQL y sus pruebas siguen pendientes para la etapa final.

Resultados y límites: [informe de pruebas](docs/PRUEBAS_RENDIMIENTO.md). Las mediciones no constituyen un SLA ni una certificación de capacidad en producción.
