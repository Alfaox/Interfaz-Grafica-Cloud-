"""Operaciones de dominio: autorización, validación y escritura transaccional."""
from contextlib import contextmanager
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import (Asistencia, AuditLog, Collera, Cuadrilla, Jornada, Participacion,
                     Pesaje, Temporada, User)


def auditar(actor, accion, detalle):
    AuditLog.objects.create(usuario=actor, accion=accion, detalle=str(detalle)[:200])


def denegar(actor, detalle):
    auditar(actor, 'ACCESO_DENEGADO', detalle)
    raise PermissionDenied


def autorizar_jornada(actor, jornada, escritura=False):
    if actor.rol == User.Rol.ADMIN and not escritura:
        return
    if actor.rol != User.Rol.JEFE or jornada.jefe_id != actor.pk:
        denegar(actor, f'Jornada {jornada.pk}: operación no autorizada')


def jornadas_para(actor):
    qs = Jornada.objects.select_related('cuadrilla', 'jefe', 'temporada', 'cuartel__huerto__predio')
    if actor.rol == User.Rol.ADMIN:
        return qs
    if actor.rol == User.Rol.JEFE:
        return qs.filter(jefe=actor)
    return qs.filter(asistencias__trabajador=actor).distinct()


def pesajes_para(actor):
    qs = Pesaje.objects.select_related('participacion__jornada__cuadrilla', 'participacion__jornada__cuartel__huerto__predio',
                                      'participacion__collera', 'responsable')
    if actor.rol == User.Rol.ADMIN:
        return qs
    if actor.rol == User.Rol.JEFE:
        return qs.filter(participacion__jornada__jefe=actor)
    return qs.filter(Q(participacion__collera__trabajador_uno=actor) | Q(participacion__collera__trabajador_dos=actor))


@transaction.atomic
def formar_collera(actor, datos):
    if actor.rol != User.Rol.ADMIN:
        raise PermissionDenied
    personas = [datos['trabajador_uno'], datos['trabajador_dos']]
    list(User.objects.select_for_update().filter(pk__in=[p.pk for p in personas]).order_by('pk'))
    if personas[0].pk == personas[1].pk:
        raise ValidationError('Selecciona dos trabajadores distintos.')
    for persona in personas:
        if persona.rol != User.Rol.TRABAJADOR or not persona.is_active:
            raise ValidationError('Los integrantes deben ser trabajadores activos.')
        if Collera.objects.filter(Q(trabajador_uno=persona) | Q(trabajador_dos=persona), activa=True).exists():
            raise ValidationError(f'{persona.get_full_name() or persona.username} ya pertenece a una collera activa.')
    obj = Collera(**datos)
    obj.full_clean()
    obj.save()
    auditar(actor, 'COLLERA_CREADA', obj)
    return obj


@transaction.atomic
def abrir_jornada(actor, datos):
    if actor.rol != User.Rol.JEFE:
        raise PermissionDenied
    temporada = Temporada.objects.select_for_update().get(pk=datos['temporada'].pk)
    equipo = Cuadrilla.objects.select_for_update().get(pk=datos['cuadrilla'].pk)
    if equipo.jefe_id != actor.pk:
        raise PermissionDenied
    if not temporada.activa or not temporada.inicio <= datos['fecha'] <= temporada.fin:
        raise ValidationError('La fecha debe pertenecer a una temporada abierta.')
    cuartel = datos['cuartel']
    if not cuartel.activo or not cuartel.huerto.predio.activo:
        raise ValidationError('Elige un cuartel y predio activos.')
    colleras = list(Collera.objects.select_for_update().filter(cuadrilla=equipo, activa=True))
    if not colleras:
        raise ValidationError('La cuadrilla necesita al menos una collera activa.')
    if Participacion.objects.filter(collera__in=colleras, fecha=datos['fecha']).exists():
        raise ValidationError('Una collera ya está asignada a otra jornada de esta fecha.')
    jornada = Jornada(jefe=actor, **datos)
    jornada.full_clean()
    jornada.save()
    for collera in colleras:
        Participacion.objects.create(jornada=jornada, collera=collera, fecha=jornada.fecha)
        for persona in collera.integrantes:
            if not persona.is_active or persona.rol != User.Rol.TRABAJADOR:
                raise ValidationError('Todos los integrantes deben ser trabajadores activos.')
            if Asistencia.objects.filter(trabajador=persona, jornada__fecha=jornada.fecha).exists():
                raise ValidationError('Un trabajador ya está asignado a una jornada de esta fecha.')
            Asistencia.objects.create(jornada=jornada, trabajador=persona)
    auditar(actor, 'JORNADA_ABIERTA', jornada)
    return jornada


@contextmanager
def jornada_bloqueada(actor, jornada, escritura=True, permitir_cerrada=False):
    autorizar_jornada(actor, jornada, escritura)
    # El mismo orden de bloqueos se usa al cerrar temporada y modificar registros.
    with transaction.atomic():
        temporada = Temporada.objects.select_for_update().get(pk=jornada.temporada_id)
        actual = Jornada.objects.select_for_update().get(pk=jornada.pk)
        if not temporada.activa or (actual.cerrada and not permitir_cerrada):
            raise ValidationError('La jornada o su temporada está cerrada; no admite modificaciones.')
        yield actual


def guardar_pesaje(actor, jornada, datos, pesaje=None):
    with jornada_bloqueada(actor, jornada):
        participacion = datos['participacion']
        if participacion.jornada_id != jornada.pk:
            raise ValidationError('La collera no pertenece a esta jornada.')
        if pesaje and pesaje.participacion.jornada_id != jornada.pk:
            raise PermissionDenied
        obj = pesaje or Pesaje(responsable=actor)
        anterior = obj.kilos if obj.pk else None
        for key, value in datos.items():
            setattr(obj, key, value)
        obj.full_clean()
        obj.save()
        auditar(actor, 'PESAJE_CORREGIDO' if anterior else 'PESAJE_CREADO',
                f'Pesaje {obj.pk} · {participacion} · {anterior or 0} → {obj.kilos} kg')
        return obj


def marcar_asistencia(actor, asistencia, accion, hora=None):
    with jornada_bloqueada(actor, asistencia.jornada):
        a = Asistencia.objects.select_for_update().get(pk=asistencia.pk)
        if accion == 'entrada':
            if a.entrada or a.ausente:
                raise ValidationError('Ya existe una entrada o está marcado ausente.')
            a.entrada = hora
        elif accion == 'salida':
            if not a.entrada or a.salida or not hora or hora <= a.entrada:
                raise ValidationError('La salida requiere entrada previa y debe ser posterior a ella.')
            a.salida = hora
        elif accion == 'ausente':
            if a.entrada:
                raise ValidationError('No puedes marcar ausente a quien tiene entrada.')
            a.ausente = True
        else:
            raise ValidationError('Acción no válida.')
        a.validada = False
        a.full_clean()
        a.save()
        auditar(actor, 'ASISTENCIA_' + accion.upper(), f'{a.trabajador.username} · jornada {a.jornada_id}')


def validar_asistencia(actor, jornada):
    with jornada_bloqueada(actor, jornada):
        jornada.asistencias.filter(Q(entrada__isnull=False) | Q(ausente=True)).update(validada=True)
        auditar(actor, 'ASISTENCIA_VALIDADA', jornada)


def cerrar_jornada(actor, jornada):
    with jornada_bloqueada(actor, jornada) as actual:
        actual.cerrada = True
        actual.cerrada_en = timezone.now()
        actual.save(update_fields=['cerrada', 'cerrada_en'])
        auditar(actor, 'JORNADA_CERRADA', actual)


def reabrir_jornada(actor, jornada, motivo):
    if actor.rol != User.Rol.ADMIN:
        denegar(actor, f'Reapertura no autorizada: jornada {jornada.pk}')
    if len(motivo.strip()) < 8:
        raise ValidationError('Explica el motivo con al menos 8 caracteres.')
    with jornada_bloqueada(actor, jornada, escritura=False, permitir_cerrada=True) as actual:
        if not actual.cerrada:
            raise ValidationError('La jornada ya está abierta.')
        actual.cerrada = False
        actual.cerrada_en = None
        actual.save(update_fields=['cerrada', 'cerrada_en'])
        auditar(actor, 'JORNADA_REABIERTA', f'{actual}: {motivo}')


@transaction.atomic
def cerrar_temporada(actor, temporada):
    if actor.rol != User.Rol.ADMIN:
        raise PermissionDenied
    temporada = Temporada.objects.select_for_update().get(pk=temporada.pk)
    temporada.activa = False
    temporada.save(update_fields=['activa'])
    auditar(actor, 'TEMPORADA_CERRADA', temporada)


@transaction.atomic
def editar_usuario(actor, pk, datos):
    if actor.rol != User.Rol.ADMIN:
        raise PermissionDenied
    # Orden estable para conservar al menos un administrador activo.
    candidatos = User.objects.select_for_update().filter(Q(rol=User.Rol.ADMIN) | Q(pk=pk)).order_by('pk')
    usuarios = {u.pk: u for u in candidatos}
    actual = usuarios[pk]
    nuevo_rol, activo = datos['rol'], datos['is_active']
    if actual.pk == actor.pk and (nuevo_rol != User.Rol.ADMIN or not activo):
        raise ValidationError('No puedes quitarte el perfil administrador ni desactivar tu propia cuenta.')
    if actual.is_superuser and nuevo_rol != User.Rol.ADMIN:
        raise ValidationError('Un superusuario debe conservar el perfil Administrador.')
    if actual.rol == User.Rol.ADMIN and actual.is_active and (nuevo_rol != User.Rol.ADMIN or not activo):
        if not any(u.pk != pk and u.rol == User.Rol.ADMIN and u.is_active for u in usuarios.values()):
            raise ValidationError('Debe quedar al menos un administrador activo.')
    if nuevo_rol != User.Rol.TRABAJADOR or not activo:
        if Collera.objects.filter(Q(trabajador_uno=actual) | Q(trabajador_dos=actual), activa=True).exists():
            raise ValidationError('Desarma primero la collera activa de este trabajador.')
    if nuevo_rol != User.Rol.JEFE or not activo:
        if actual.cuadrillas.exists() or actual.jornadas_responsable.filter(cerrada=False, temporada__activa=True).exists():
            raise ValidationError('Reasigna sus cuadrillas y cierra sus jornadas abiertas antes de cambiar el perfil o desactivar al jefe.')
    cambios = []
    permitidos = ['username', 'first_name', 'last_name', 'email', 'rol', 'is_active']
    for key in permitidos:
        anterior, nuevo = getattr(actual, key), datos[key]
        if anterior != nuevo:
            cambios.append(f'{key}: {anterior} → {nuevo}')
            setattr(actual, key, nuevo)
    actual.full_clean()
    actual.save(update_fields=permitidos)
    if cambios:
        auditar(actor, 'USUARIO_EDITADO', f'Usuario {actual.pk}: {", ".join(cambios)}')
        if any(c.startswith('rol:') for c in cambios):
            auditar(actor, 'ROL_CAMBIADO', f'Usuario {actual.pk}: {next(c for c in cambios if c.startswith("rol:"))}')
    return actual


@transaction.atomic
def editar_catalogo(actor, modelo, pk, datos):
    if actor.rol != User.Rol.ADMIN:
        raise PermissionDenied
    from .models import Cuartel, Huerto
    obj = modelo.objects.select_for_update().get(pk=pk)
    # Evitar cambiar a posteriori la ubicación/cultivo de una cosecha registrada.
    if isinstance(obj, Huerto) and datos['predio'].pk != obj.predio_id:
        if Jornada.objects.filter(cuartel__huerto=obj).exists():
            raise ValidationError('Un huerto con jornadas no puede trasladarse de predio. Crea otro huerto para conservar el historial.')
        if not datos['predio'].activo:
            raise ValidationError('El predio de destino debe estar activo.')
    if isinstance(obj, Cuartel):
        estructura_cambia = datos['huerto'].pk != obj.huerto_id or datos['cultivo'].pk != obj.cultivo_id
        if estructura_cambia and obj.jornadas.exists():
            raise ValidationError('No puedes cambiar el huerto o cultivo de un cuartel con jornadas. Crea un nuevo cuartel.')
        if datos['huerto'].pk != obj.huerto_id and not datos['huerto'].predio.activo:
            raise ValidationError('El huerto de destino debe pertenecer a un predio activo.')
    if isinstance(obj, Temporada):
        if obj.jornadas.filter(Q(fecha__lt=datos['inicio']) | Q(fecha__gt=datos['fin'])).exists():
            raise ValidationError('Las fechas no pueden dejar fuera jornadas ya registradas.')
    if isinstance(obj, Cuadrilla) and obj.jefe_id != datos['jefe'].pk:
        if obj.jornadas.filter(cerrada=False, temporada__activa=True).exists():
            raise ValidationError('Cierra las jornadas abiertas antes de reasignar al jefe. Las jornadas anteriores conservarán su responsable.')
    # Lista explícita por modelo: nunca aceptar campos de control desde el cliente.
    campos = {
        'predio': ['nombre', 'codigo', 'ubicacion'], 'huerto': ['nombre', 'codigo', 'predio'],
        'cultivo': ['nombre'], 'cuartel': ['nombre', 'codigo', 'huerto', 'cultivo', 'superficie'],
        'temporada': ['nombre', 'inicio', 'fin'], 'cuadrilla': ['nombre', 'jefe'], 'collera': ['nombre'],
    }[obj._meta.model_name]
    cambios = []
    for key in campos:
        antes, despues = getattr(obj, key), datos[key]
        if antes != despues:
            cambios.append(f'{key}: {antes} → {despues}')
        setattr(obj, key, despues)
    obj.full_clean()
    obj.save(update_fields=campos)
    if cambios:
        auditar(actor, 'CATALOGO_EDITADO', f'{obj._meta.model_name} {obj.pk}: {", ".join(cambios)}')
    return obj


@transaction.atomic
def trasladar_collera(actor, collera, destino, motivo):
    if actor.rol != User.Rol.ADMIN:
        raise PermissionDenied
    if len(motivo.strip()) < 8:
        raise ValidationError('Indica un motivo de al menos 8 caracteres.')
    # Apertura de jornada bloquea primero cuadrilla, luego colleras.
    equipos = list(Cuadrilla.objects.select_for_update().filter(pk__in=[collera.cuadrilla_id, destino.pk]).order_by('pk'))
    actual = Collera.objects.select_for_update().get(pk=collera.pk)
    destino = next((c for c in equipos if c.pk == destino.pk), None)
    if actual.cuadrilla_id != collera.cuadrilla_id:
        raise ValidationError('La collera cambió de cuadrilla. Recarga antes de intentar el traslado.')
    if not actual.activa:
        raise ValidationError('Solo puedes trasladar colleras activas.')
    if not destino or destino.pk == actual.cuadrilla_id:
        raise ValidationError('Selecciona una cuadrilla de destino diferente.')
    if not destino.jefe.is_active or destino.jefe.rol != User.Rol.JEFE:
        raise ValidationError('La cuadrilla de destino necesita un jefe activo.')
    origen = actual.cuadrilla
    actual.cuadrilla = destino
    actual.save(update_fields=['cuadrilla'])
    # No se tocan participaciones, asistencias ni pesajes de jornadas ya abiertas.
    auditar(actor, 'COLLERA_TRASLADADA', f'{actual}: {origen} → {destino}. {motivo}')
    return actual


def configurar_autogestion(actor, jornada, habilitada):
    with jornada_bloqueada(actor, jornada) as actual:
        actual.autogestion_habilitada = habilitada
        actual.save(update_fields=['autogestion_habilitada'])
        auditar(actor, 'AUTOGESTION_CONFIGURADA', f'Jornada {actual.pk}: {"habilitada" if habilitada else "deshabilitada"}')


def marcar_propia(actor, asistencia, accion):
    if actor.rol != User.Rol.TRABAJADOR or asistencia.trabajador_id != actor.pk:
        denegar(actor, f'Autogestión ajena: asistencia {asistencia.pk}')
    vigente = Jornada.objects.get(pk=asistencia.jornada_id)
    if not vigente.autogestion_habilitada:
        denegar(actor, f'Autogestión deshabilitada: jornada {asistencia.jornada_id}')
    if accion not in ['entrada', 'salida']:
        raise ValidationError('Solo puedes registrar tu entrada o salida.')
    ahora = timezone.localtime()
    if vigente.fecha != ahora.date():
        raise ValidationError('Solo puedes marcar la jornada de hoy.')
    with transaction.atomic():
        temporada = Temporada.objects.select_for_update().get(pk=vigente.temporada_id)
        jornada = Jornada.objects.select_for_update().get(pk=asistencia.jornada_id)
        if not temporada.activa or jornada.cerrada:
            raise ValidationError('La jornada o temporada está cerrada.')
        if not jornada.autogestion_habilitada:
            raise ValidationError('El jefe deshabilitó la autogestión.')
        actual = Asistencia.objects.select_for_update().get(pk=asistencia.pk)
        hora = ahora.time().replace(tzinfo=None, microsecond=0)
        if actual.ausente:
            raise ValidationError('Estás marcado ausente. Solicita al jefe revisar tu asistencia.')
        if accion == 'entrada':
            if actual.entrada:
                raise ValidationError('Ya registraste tu entrada.')
            actual.entrada = hora
        else:
            if not actual.entrada or actual.salida or hora <= actual.entrada:
                raise ValidationError('La salida requiere una entrada anterior y no puede registrarse dos veces.')
            actual.salida = hora
        actual.validada = False
        actual.full_clean()
        actual.save()
        auditar(actor, 'ASISTENCIA_PROPIA', f'Asistencia {actual.pk}: {accion} {hora:%H:%M:%S} · pendiente de validación')


def editar_observaciones(actor, jornada, observaciones):
    observaciones = observaciones.strip()
    if len(observaciones) > 500:
        raise ValidationError('Las observaciones no pueden superar 500 caracteres.')
    with jornada_bloqueada(actor, jornada) as actual:
        anterior = actual.observaciones
        actual.observaciones = observaciones
        actual.full_clean()
        actual.save(update_fields=['observaciones'])
        if anterior != observaciones:
            # Eventos segmentados conservan ambos valores sin superar los 200 caracteres.
            auditar(actor, 'OBSERVACIONES_EDITADAS', f'Jornada {actual.pk}: observaciones actualizadas.')
            for etiqueta, texto in [('ANTES', anterior), ('DESPUES', observaciones)]:
                for posicion in range(0, len(texto) or 1, 150):
                    auditar(actor, 'OBSERVACIONES_' + etiqueta, f'Jornada {actual.pk} · parte {posicion//150+1}: {texto[posicion:posicion+150]}')
