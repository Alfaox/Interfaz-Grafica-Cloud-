# AgroKODIT · Evidencia de rendimiento y concurrencia

## Resultado

La corrida final completó los seis escenarios sin errores de base de datos y con las comprobaciones de integridad satisfechas. Los rechazos por validación son esperados cuando varias operaciones intentan marcar la misma entrada, formar colleras con los mismos integrantes o escribir después del cierre.

- Fecha UTC: 2026-10-27T00:20:38.177769+00:00
- Entorno: Darwin x86_64; Python 3.14.6; Django 5.2.18; SQLite 3.53.4.
- Volumen: 10432 pesajes, de los que 10.000 se agregaron únicamente a la copia temporal.
- Concurrencia: 8 conexiones de trabajo; 80 consultas de reportes en total.
- SQLite: modo IMMEDIATE, timeout 20 segundos.
- Huella del archivo original sin cambios: True.

| Escenario | Aceptadas | Rechazos esperados | Errores técnicos | p95 (ms) | Integridad |
| --- | ---: | ---: | ---: | ---: | --- |
| Reportes concurrentes, con middleware y plantillas | 80 | 0 | 0 | 2211.0 | HTTP 200 en todas las consultas |
| Pesajes simultáneos en la misma jornada | 8 | 0 | 0 | 122.66 | Correcta |
| Entradas de ocho trabajadores diferentes | 8 | 0 | 0 | 182.53 | Correcta |
| Creación simultánea de colleras con los mismos integrantes | 1 | 7 | 0 | 62.35 | Correcta |
| Misma entrada solicitada simultáneamente | 1 | 7 | 0 | 114.95 | Correcta |
| Cierre de jornada simultáneo con pesajes | 1 | 7 | 0 | 47.64 | Correcta |

El p95 es el tiempo por debajo del cual terminó el 95 % de las operaciones; no es el tiempo máximo. Los tiempos de escritura incluyen también los rechazos esperados. La muestra de ocho escrituras por escenario es pequeña y no demuestra capacidad sostenida.

## Qué se comprobó

1. Consultas de reportes: código HTTP 200 para las 80 solicitudes autenticadas, con middleware y renderizado de plantillas.
2. Pesajes simultáneos: cada operación aceptada corresponde a un nuevo pesaje persistido; no se perdieron escrituras aceptadas.
3. Asistencia de ocho personas: ocho entradas distintas persistidas.
4. Colleras competidoras: exactamente una collera activa formada con los dos integrantes; las otras solicitudes fueron rechazadas.
5. Entrada duplicada: exactamente una marca y un evento de auditoría para ese trabajador; los siete duplicados fueron rechazados.
6. Cierre frente a pesajes: la jornada terminó cerrada, el servidor rechazó una escritura posterior y no se encontraron eventos de pesaje posteriores al evento de cierre. Los pesajes que alcanzan el bloqueo antes del cierre pueden aceptarse; los demás deben rechazarse.

## Hallazgos y correcciones

La primera corrida con transacciones diferidas produjo errores `OperationalError: database is locked`: siete de los ocho pesajes simultáneos fallaron técnicamente. Se conservó la evidencia en [rendimiento_antes.json](rendimiento_antes.json).

Se configuraron transacciones SQLite `IMMEDIATE` y una espera de 20 segundos. Así, las escrituras esperan su turno desde el inicio de la transacción, en vez de competir al promover una transacción lectora. No se agregaron reintentos que pudieran duplicar pesajes. Esta configuración serializa escritores a nivel de SQLite; no equivale a bloqueo por fila. Referencia: [documentación oficial de Django sobre SQLite](https://docs.djangoproject.com/en/5.2/ref/databases/#database-is-locked-errors).

El reporte se paginó a 50 pesajes. Los totales, rankings y exportación siguen incluyendo todos los resultados filtrados; las páginas conservan los filtros. El ranking individual se obtiene en dos consultas agregadas, no una consulta por trabajador o pesaje.

Las corridas antes/después son exploratorias: entre ellas también se incorporó el ranking individual y se modificó la paginación. No son un experimento controlado para atribuir la diferencia de tiempos a un único ajuste.

## Reproducir

Desde la raíz, con el entorno virtual activado:

```bash
python scripts/probar_rendimiento.py --workers 8 --requests 80 --extra-pesajes 10000 --output docs/rendimiento_despues.json
```

El script requiere la base SQLite local con sus migraciones aplicadas. Crea una copia temporal consistente, ejecuta la prueba sobre ella y la elimina al terminar. Sale con código 1 si un escenario tiene errores técnicos o falla una comprobación de integridad. Las solicitudes rechazadas correctamente por las reglas de negocio no se consideran errores técnicos.

La ejecución final debe hacerse sin otras pruebas o tareas intensivas ejecutándose en paralelo en el mismo equipo. La huella puede cambiar por acciones externas si otra persona usa la aplicación durante la prueba; el script solo abre el original para lectura y respaldo.

## Alcance y límites

- Lecturas con cliente HTTP interno de Django y sesiones autenticadas; escrituras mediante servicios de dominio desde hilos con conexiones independientes.
- No se midieron latencia de red, navegador, servidor WSGI/ASGI, archivos estáticos ni recursos cloud.
- La prueba usa una copia SQLite y un equipo local. No certifica MySQL, alta concurrencia, disponibilidad ni un SLA de producción.
- Las funciones de observaciones y ranking cuentan además con pruebas de permisos, filtrado, historial, exactitud del reparto, empates, CSRF, cierre y límite de longitud.
- La prueba no sustituye la evaluación visual, accesibilidad ni la carga prolongada sobre el despliegue real.

## Archivos de evidencia

- [Resultado inicial](rendimiento_antes.json).
- [Resultado final](rendimiento_despues.json).
- [Script reproducible](../scripts/probar_rendimiento.py).
