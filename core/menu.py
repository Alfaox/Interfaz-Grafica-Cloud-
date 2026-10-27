from .models import User

A, J, T = User.Rol.ADMIN, User.Rol.JEFE, User.Rol.TRABAJADOR

# (etiqueta, nombre de url, descripción, roles con acceso)
MENU = [
    ("Inicio", "home", "Resumen de tu jornada y accesos rápidos.", (A, J, T)),
    ("Usuarios y roles", "usuarios", "Crear cuentas y asignar rol.", (A,)),
    ("Predios y temporadas", "predios", "Predios, huertos, cuarteles y temporadas.", (A,)),
    ("Reportes y rankings", "reportes", "Producción consolidada y exportación.", (A, J)),
    ("Auditoría", "auditoria", "Registro de accesos y acciones críticas.", (A,)),
    ("Mi cuadrilla", "cuadrilla", "Colleras y trabajadores asignados.", (A, J)),
    ("Asistencia", "asistencia", "Registrar asistencia de la jornada.", (J,)),
    ("Registrar kilos", "kilos", "Ingreso de producción por collera.", (J,)),
    ("Cerrar jornada", "cierre", "Resumen y bloqueo diario de datos.", (A, J)),
    ("Mi asistencia", "mi_asistencia", "Consulta de tu asistencia.", (T,)),
    ("Mi producción", "mi_produccion", "Consulta de tus kilos y los de tu collera.", (T,)),
]


def items_for(rol):
    items = [m for m in MENU if rol in m[3]]
    if rol == A:
        etiquetas = {'cuadrilla': 'Cuadrillas y colleras', 'cierre': 'Supervisar jornadas'}
        items = [(etiquetas.get(l[1], l[0]), *l[1:]) for l in items]
    return items
