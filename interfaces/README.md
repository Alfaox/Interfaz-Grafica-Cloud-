# AgroKODIT · Prototipo de interfaces

Interfaces independientes basadas en el Informe 2 (EVA2). No modifican Django, sus plantillas, configuración ni base de datos. Son HTML, CSS y JavaScript sin instalación ni compilación.

## Abrir

Abre `index.html` en el navegador. En macOS, desde la carpeta del proyecto:

```bash
open interfaces/index.html
```

Alternativamente, sirve solamente esta carpeta:

```bash
python3 -m http.server 8080 --directory interfaces
```

Abre http://localhost:8080. Para detener ese servidor, presiona Ctrl+C.

En la primera pantalla elige un perfil. Puedes cambiar de perfil desde el selector superior. No necesitas credenciales: es una selección de vistas de demostración, no un inicio de sesión real.

## Pantallas

| Perfil | Interfaces |
| --- | --- |
| Administrador | Resumen, predios y temporadas, usuarios, cuadrillas y colleras, supervisión/reapertura de jornadas, reportes, auditoría |
| Jefe de Cuadrilla | Resumen de su equipo, cuadrillas, asistencia, kilos, cierre, reportes de su equipo |
| Trabajador | Resumen personal, asistencia propia, producción de su collera |

## Recorrido sugerido

1. Entra como Administrador y revisa el resumen y el árbol Predio → Huerto → Cuartel.
2. Crea un predio, un huerto y un cuartel. Prueba la búsqueda de usuarios.
3. En cuadrillas, forma una collera con Felipe y Catalina, los dos trabajadores inicialmente disponibles.
4. Cambia a Jefe de Cuadrilla. Registra un pesaje, una calidad y, si corresponde, merma y motivo. Corrige el pesaje antes del cierre.
5. Registra salidas en asistencia y valida las marcas.
6. Revisa el resumen de cierre y confirma el cierre. Comprueba que ya no puedas ingresar kilos ni modificar marcas.
7. Cambia a Administrador, revisa la bitácora y reabre la jornada justificando el motivo.
8. Cambia a Trabajador para ver su asistencia y los kilos de su collera.
9. En reportes, filtra por fechas y ubicación, descarga CSV o abre el diálogo de impresión para guardar como PDF.

## Reglas representadas en la interfaz

- Colleras de exactamente dos trabajadores distintos y disponibles (HU-11).
- Kilos mayores que cero, con hasta dos decimales; merma no negativa y motivo cuando existe (HU-30 a HU-32).
- Correcciones y asistencia habilitadas solamente en la jornada abierta (HU-34, HU-38).
- Salida posterior a la entrada; ausente no puede tener entrada (HU-18 a HU-21).
- Resumen previo al cierre, confirmación y reapertura por administrador con motivo (HU-37 a HU-40).
- Selección de vistas y datos por perfil; trabajador consulta los pesajes de las colleras en las que participó.
- Cierre de temporada deja la jornada de ejemplo en modo de solo lectura.
- Historial de pesajes conserva la cuadrilla y los integrantes originales. El traslado de una collera se muestra como asignación para la próxima jornada.

## Alcance y límites

Este es un prototipo gráfico interactivo, no la implementación del backend. La selección de perfiles y los controles JavaScript no proporcionan autenticación ni autorización seguras. Las reglas deberán validarse nuevamente en Django y la base de datos cuando se autorice esa integración.

Los cambios y la bitácora se guardan en `localStorage` con la clave `agrokodit-interfaces-v1`, únicamente en este navegador y origen. Si el almacenamiento no está disponible, se mantienen en memoria hasta cerrar o recargar. No ingreses información real. El botón «Restablecer demo» recupera los ejemplos. Al cambiar de día se reconstruye la jornada de ejemplo.

Los gráficos y totales se calculan a partir de los pesajes de ejemplo y los que ingreses. Los kilos representan a la collera completa; no se inventa un reparto individual. La asistencia contiene una jornada de ejemplo, no un historial semanal completo. No se implementan autogestión de asistencia, cambio de contraseña, entrega de avisos externos ni procedimientos almacenados.

La exportación es CSV, no XLSX. La opción PDF usa el diálogo de impresión del navegador. Estos mecanismos permiten revisar el diseño y aún no satisfacen la exportación de archivos XLSX/PDF del backend de HU-50.

El diseño usa iconos SVG y gráficos CSS locales. Las tipografías DM Sans y Manrope se solicitan a Google Fonts; sin conexión se utilizan fuentes del sistema. Navegación por teclado, etiquetas de formularios, mensajes de estado y diseño adaptable desde 360 px están incluidos; la comprobación visual en un navegador y con lector de pantalla sigue siendo necesaria.
