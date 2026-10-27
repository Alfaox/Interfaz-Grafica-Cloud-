import csv
from datetime import timedelta
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from . import forms, reporting, services
from .menu import items_for
from .models import (Asistencia, AuditLog, Collera, Cuadrilla, Cuartel, Cultivo, Huerto,
                     Jornada, Pesaje, Predio, Temporada, User)
from .permissions import role_required

A, J, T = User.Rol.ADMIN, User.Rol.JEFE, User.Rol.TRABAJADOR


def error_form(form, exc):
    form.add_error(None, 'La operación coincide con otro registro. Revisa los datos.' if isinstance(exc, IntegrityError) else ' '.join(exc.messages))


def ejecutar(request, operacion, destino):
    try:
        operacion()
        messages.success(request, 'Operación guardada correctamente.')
    except (ValidationError, IntegrityError) as exc:
        messages.error(request, 'La operación coincide con otro registro.' if isinstance(exc, IntegrityError) else ' '.join(exc.messages))
    return redirect(destino)


def seleccion_jornada(request):
    qs = services.jornadas_para(request.user)
    if request.GET.get('jornada'):
        identificador = request.GET['jornada']
        if not identificador.isdecimal():
            return None, qs
        jornada = get_object_or_404(Jornada, pk=identificador)
        services.autorizar_jornada(request.user, jornada)
    else:
        jornada = qs.first()
    return jornada, qs


@role_required(A, J, T)
def home(request):
    hoy = timezone.localdate()
    qs = services.pesajes_para(request.user)
    datos = reporting.resumen(qs.filter(participacion__jornada__fecha=hoy))
    datos.update({'accesos': [m for m in items_for(request.user.rol) if m[1] != 'home'],
                  'hoy': hoy, 'actividad': AuditLog.objects.all()[:4] if request.user.rol == A else AuditLog.objects.filter(usuario=request.user)[:4],
                  'jornadas': services.jornadas_para(request.user).filter(fecha=hoy),
                  'semanal': reporting.resumen(qs.filter(participacion__jornada__fecha__range=(hoy-timedelta(days=6), hoy)))})
    return render(request, 'core/home.html', datos)


@role_required(A)
def usuarios(request):
    qs = User.objects.order_by('rol', 'username')
    if request.GET.get('q'):
        q = request.GET['q'][:100]
        qs = qs.filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    return render(request, 'core/usuarios.html', {'usuarios': qs, 'q': request.GET.get('q', '')})


@role_required(A)
def usuario_nuevo(request):
    form = forms.UsuarioForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            u = form.save()
            services.auditar(request.user, 'USUARIO_CREADO', f'{u.username} ({u.rol})')
        messages.success(request, f'Usuario {u.username} creado.')
        return redirect('usuarios')
    return render(request, 'core/form.html', {'form': form, 'titulo': 'Nuevo usuario', 'volver': 'usuarios', 'descripcion': 'Crea una cuenta y asigna sus permisos.'})


@role_required(A)
def auditoria(request):
    return render(request, 'core/auditoria.html', {'logs': AuditLog.objects.select_related('usuario')[:200]})


@role_required(A)
def predios(request):
    return render(request, 'core/predios.html', {'predios': Predio.objects.prefetch_related('huertos__cuarteles__cultivo'), 'temporadas': Temporada.objects.all(), 'cultivos': Cultivo.objects.all()})


CATALOGOS = {
    'predio': (forms.PredioForm, 'Nuevo predio', 'predios'),
    'huerto': (forms.HuertoForm, 'Nuevo huerto', 'predios'),
    'cultivo': (forms.CultivoForm, 'Nuevo cultivo', 'predios'),
    'cuartel': (forms.CuartelForm, 'Nuevo cuartel', 'predios'),
    'temporada': (forms.TemporadaForm, 'Nueva temporada', 'predios'),
    'cuadrilla': (forms.CuadrillaForm, 'Nueva cuadrilla', 'cuadrilla'),
    'collera': (forms.ColleraForm, 'Formar collera', 'cuadrilla'),
}


@role_required(A)
def catalogo_nuevo(request, tipo):
    if tipo not in CATALOGOS:
        from django.http import Http404
        raise Http404
    clase, titulo, volver = CATALOGOS[tipo]
    form = clase(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                if tipo == 'collera':
                    services.formar_collera(request.user, form.cleaned_data)
                else:
                    obj = form.save()
                    services.auditar(request.user, tipo.upper() + '_CREADO', obj)
            messages.success(request, 'Registro creado correctamente.')
            return redirect(volver)
        except (ValidationError, IntegrityError) as exc:
            error_form(form, exc)
    return render(request, 'core/form.html', {'form': form, 'titulo': titulo, 'volver': volver, 'descripcion': 'Completa los datos para organizar tu operación agrícola.'})


@role_required(A)
@require_POST
def estado_catalogo(request, tipo, pk):
    modelos = {'predio': Predio, 'cuartel': Cuartel, 'temporada': Temporada, 'collera': Collera}
    if tipo not in modelos:
        from django.http import Http404
        raise Http404
    obj = get_object_or_404(modelos[tipo], pk=pk)
    destino = 'cuadrilla' if tipo == 'collera' else 'predios'
    def cambiar():
        if tipo == 'temporada':
            services.cerrar_temporada(request.user, obj)
        else:
            with transaction.atomic():
                # Bloqueo compartido con apertura de jornada y creación de colleras.
                if tipo == 'collera':
                    list(User.objects.select_for_update().filter(pk__in=[obj.trabajador_uno_id, obj.trabajador_dos_id]).order_by('pk'))
                campo = 'activa' if tipo == 'collera' else 'activo'
                # Una collera desarmada nunca se reactiva: se crea una nueva para preservar integrantes.
                setattr(obj, campo, False if tipo == 'collera' else not getattr(obj, campo))
                obj.save(update_fields=[campo])
                services.auditar(request.user, 'ESTADO_ACTUALIZADO', f'{tipo}: {obj}')
    return ejecutar(request, cambiar, destino)


@role_required(A, J)
def cuadrilla(request):
    equipos = Cuadrilla.objects.select_related('jefe').prefetch_related('colleras__trabajador_uno', 'colleras__trabajador_dos')
    if request.user.rol == J:
        equipos = equipos.filter(jefe=request.user)
    return render(request, 'core/cuadrilla.html', {'cuadrillas': equipos})


@role_required(J)
def jornada_nueva(request):
    form = forms.JornadaForm(request.POST if request.method == 'POST' else None, actor=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            j = services.abrir_jornada(request.user, form.cleaned_data)
            messages.success(request, 'Jornada abierta. Ya puedes registrar asistencia y kilos.')
            return redirect(reverse('asistencia') + f'?jornada={j.pk}')
        except (ValidationError, IntegrityError) as exc:
            error_form(form, exc)
    return render(request, 'core/form.html', {'form': form, 'titulo': 'Abrir jornada', 'volver': 'cuadrilla', 'descripcion': 'Define tu equipo, ubicación y labor. Los integrantes se conservan en el historial.'})


@role_required(J)
def asistencia(request):
    j, jornadas = seleccion_jornada(request)
    return render(request, 'core/asistencia.html', {'jornada': j, 'jornadas': jornadas, 'asistencias': j.asistencias.select_related('trabajador', 'jornada') if j else []})


@role_required(J)
def asistencia_marca(request, pk):
    a = get_object_or_404(Asistencia.objects.select_related('jornada'), pk=pk)
    services.autorizar_jornada(request.user, a.jornada, escritura=True)
    form = forms.MarcaForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            services.marcar_asistencia(request.user, a, form.cleaned_data['accion'], form.cleaned_data['hora'])
            messages.success(request, 'Asistencia guardada.')
            return redirect(reverse('asistencia') + f'?jornada={a.jornada_id}')
        except ValidationError as exc:
            error_form(form, exc)
    return render(request, 'core/form.html', {'form': form, 'titulo': f'Asistencia · {a.trabajador.get_full_name() or a.trabajador.username}', 'volver': 'asistencia', 'descripcion': 'Las salidas requieren una entrada previa y deben ser posteriores a ella.'})


@role_required(J)
@require_POST
def asistencia_validar(request, pk):
    j = get_object_or_404(Jornada, pk=pk)
    return ejecutar(request, lambda: services.validar_asistencia(request.user, j), reverse('asistencia') + f'?jornada={j.pk}')


@role_required(J)
def kilos(request):
    j, jornadas = seleccion_jornada(request)
    form = forms.PesajeForm(request.POST if request.method == 'POST' else None, jornada=j) if j else None
    if request.method == 'POST' and not j:
        messages.error(request, 'Abre una jornada antes de registrar kilos.')
        return redirect('kilos')
    if request.method == 'POST' and form.is_valid():
        try:
            services.guardar_pesaje(request.user, j, form.cleaned_data)
            messages.success(request, 'Pesaje guardado correctamente.')
            return redirect(reverse('kilos') + f'?jornada={j.pk}')
        except (ValidationError, IntegrityError) as exc:
            error_form(form, exc)
    qs = services.pesajes_para(request.user).filter(participacion__jornada=j) if j else Pesaje.objects.none()
    return render(request, 'core/kilos.html', {'form': form, 'jornada': j, 'jornadas': jornadas, 'pesajes': qs, **reporting.resumen(qs)})


@role_required(J)
def pesaje_editar(request, pk):
    obj = get_object_or_404(Pesaje.objects.select_related('participacion__jornada'), pk=pk)
    j = obj.participacion.jornada
    services.autorizar_jornada(request.user, j, escritura=True)
    form = forms.PesajeForm(request.POST if request.method == 'POST' else None, instance=obj, jornada=j)
    if request.method == 'POST' and form.is_valid():
        try:
            # Recargar el original: ModelForm valida modificando su instance en memoria.
            original = Pesaje.objects.get(pk=obj.pk)
            services.guardar_pesaje(request.user, j, form.cleaned_data, pesaje=original)
            messages.success(request, 'Pesaje corregido y auditado.')
            return redirect(reverse('kilos') + f'?jornada={j.pk}')
        except (ValidationError, IntegrityError) as exc:
            error_form(form, exc)
    return render(request, 'core/form.html', {'form': form, 'titulo': 'Corregir pesaje', 'volver': 'kilos', 'descripcion': 'Solo puedes corregir registros de una jornada abierta.', 'bloqueado': not j.editable})


@role_required(A, J)
def cierre(request):
    j, jornadas = seleccion_jornada(request)
    qs = services.pesajes_para(request.user).filter(participacion__jornada=j) if j else Pesaje.objects.none()
    asistencias = j.asistencias.all() if j else Asistencia.objects.none()
    return render(request, 'core/cierre.html', {'jornada': j, 'jornadas': jornadas, 'presentes': asistencias.filter(entrada__isnull=False).count(),
                   'sin_salida': asistencias.filter(entrada__isnull=False, salida__isnull=True).count(), **reporting.resumen(qs)})


@role_required(J)
@require_POST
def jornada_cerrar(request, pk):
    j = get_object_or_404(Jornada, pk=pk)
    if request.POST.get('confirmar') != 'si':
        messages.error(request, 'Confirma que revisaste el resumen antes del cierre.')
        return redirect(reverse('cierre') + f'?jornada={j.pk}')
    return ejecutar(request, lambda: services.cerrar_jornada(request.user, j), reverse('cierre') + f'?jornada={j.pk}')


@role_required(A)
def jornada_reabrir(request, pk):
    j = get_object_or_404(Jornada, pk=pk)
    form = forms.MotivoForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            services.reabrir_jornada(request.user, j, form.cleaned_data['motivo'])
            messages.success(request, 'Jornada reabierta con motivo registrado.')
            return redirect(reverse('cierre') + f'?jornada={j.pk}')
        except ValidationError as exc:
            error_form(form, exc)
    return render(request, 'core/form.html', {'form': form, 'titulo': 'Reabrir jornada', 'volver': 'cierre', 'descripcion': f'{j}. Justifica esta excepción para conservar la trazabilidad.'})


@role_required(A, J)
def reportes(request):
    hoy = timezone.localdate()
    form = forms.ReporteForm(request.GET or {'desde': hoy-timedelta(days=6), 'hasta': hoy}, actor=request.user)
    valido = form.is_valid()
    qs = reporting.filtrar(request.user, form.cleaned_data) if valido else Pesaje.objects.none()
    if request.GET.get('exportar') == 'csv':
        if request.user.rol != A:
            services.denegar(request.user, 'Exportación global no autorizada')
        if not valido:
            messages.error(request, 'Corrige los filtros antes de exportar.')
        else:
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = 'attachment; filename="agrokodit-produccion.csv"'
            response.write('\ufeff')
            writer = csv.writer(response, delimiter=';')
            writer.writerow(['Fecha', 'Cuadrilla', 'Collera', 'Cuartel', 'Calidad', 'Kilos', 'Merma'])
            def celda(valor):
                valor = str(valor)
                return "'" + valor if valor.startswith(('=', '+', '-', '@', '\t', '\r')) else valor
            for r in qs:
                writer.writerow([celda(x) for x in [r.participacion.jornada.fecha, r.participacion.jornada.cuadrilla,
                                r.participacion.collera, r.participacion.jornada.cuartel.nombre, r.get_calidad_display(), r.kilos, r.merma]])
            services.auditar(request.user, 'REPORTE_EXPORTADO', f'CSV · filtros: {request.GET.urlencode()[:150]}')
            return response
    parametros = request.GET.copy()
    parametros['exportar'] = 'csv'
    if not request.GET:
        parametros['desde'] = str(hoy-timedelta(days=6))
        parametros['hasta'] = str(hoy)
    parametros.pop('page', None)
    pagina = Paginator(qs.order_by('-creado', '-pk'), 50).get_page(request.GET.get('page'))
    filtros_pagina = parametros.copy()
    filtros_pagina.pop('exportar', None)
    return render(request, 'core/reportes.html', {'form': form, 'pesajes': pagina.object_list, 'pagina': pagina,
                    'filtros_pagina': filtros_pagina.urlencode(), 'ranking_trabajadores': reporting.ranking_trabajadores(qs),
                    'export_url': '?' + parametros.urlencode(), **reporting.resumen(qs, form.cleaned_data.get('hasta') if valido else hoy)})


@role_required(T)
def mi_asistencia(request):
    qs = Asistencia.objects.filter(trabajador=request.user).select_related('jornada__cuadrilla', 'jornada__temporada')
    hoy = timezone.localdate()
    semana = hoy - timedelta(days=hoy.weekday())
    horas = sum((a.horas for a in qs.filter(jornada__fecha__range=(semana, hoy))), 0)
    return render(request, 'core/mi_asistencia.html', {'asistencias': qs.order_by('-jornada__fecha'), 'horas': horas, 'hoy': hoy})


@role_required(T)
def mi_produccion(request):
    qs = services.pesajes_para(request.user)
    return render(request, 'core/mi_produccion.html', {'pesajes': qs[:200], **reporting.resumen(qs)})


@role_required(A)
def usuario_editar(request, pk):
    obj = get_object_or_404(User, pk=pk)
    form = forms.UsuarioEditarForm(request.POST if request.method == 'POST' else None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        try:
            services.editar_usuario(request.user, pk, form.cleaned_data)
            messages.success(request, 'Usuario y permisos actualizados. Los cambios se aplican desde la próxima solicitud.')
            return redirect('usuarios')
        except (ValidationError, IntegrityError) as exc:
            error_form(form, exc)
    return render(request, 'core/form.html', {'form':form, 'titulo':'Editar usuario y permisos', 'volver':'usuarios',
                   'descripcion':'Modifica los datos, el perfil o el estado de la cuenta. Las contraseñas se mantienen.'})


@role_required(A)
def catalogo_editar(request, tipo, pk):
    if tipo not in CATALOGOS:
        from django.http import Http404
        raise Http404
    clase, _, volver = CATALOGOS[tipo]
    if tipo == 'collera':
        clase = forms.ColleraEditarForm
    modelo = clase._meta.model
    obj = get_object_or_404(modelo, pk=pk)
    form = clase(request.POST if request.method == 'POST' else None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        try:
            services.editar_catalogo(request.user, modelo, pk, form.cleaned_data)
            messages.success(request, 'Catálogo actualizado. Se conservó el historial asociado.')
            return redirect(volver)
        except (ValidationError, IntegrityError) as exc:
            error_form(form, exc)
    descripcion = 'Actualiza la ficha sin borrar registros históricos.'
    if tipo == 'collera':
        descripcion = 'Puedes corregir el nombre. Para cambiar integrantes, desarma la collera y forma otra; para mover el equipo, usa Trasladar.'
    return render(request, 'core/form.html', {'form':form,'titulo':f'Editar {tipo}','volver':volver,'descripcion':descripcion})


@role_required(A)
def collera_trasladar(request, pk):
    obj = get_object_or_404(Collera.objects.select_related('cuadrilla'), pk=pk)
    form = forms.TrasladoForm(request.POST if request.method == 'POST' else None, collera=obj)
    if request.method == 'POST' and form.is_valid():
        try:
            services.trasladar_collera(request.user, obj, form.cleaned_data['destino'], form.cleaned_data['motivo'])
            messages.success(request, 'Collera trasladada para próximas jornadas. Las jornadas ya abiertas mantienen su equipo y producción.')
            return redirect('cuadrilla')
        except (ValidationError, IntegrityError) as exc:
            error_form(form, exc)
    return render(request, 'core/form.html', {'form':form,'titulo':f'Trasladar {obj.nombre}','volver':'cuadrilla',
                   'descripcion':f'Origen: {obj.cuadrilla}. El traslado se aplicará a nuevas jornadas; no mueve asistencia ni pesajes existentes.',
                   'bloqueado':not obj.activa})


@role_required(J)
@require_POST
def autogestion_configurar(request, pk):
    j = get_object_or_404(Jornada, pk=pk)
    services.autorizar_jornada(request.user, j, escritura=True)
    form = forms.AutogestionForm(request.POST)
    destino = reverse('asistencia') + f'?jornada={j.pk}'
    if form.is_valid():
        return ejecutar(request, lambda:services.configurar_autogestion(request.user,j,form.cleaned_data['habilitada']),destino)
    messages.error(request,'Revisa la configuración de autogestión.')
    return redirect(destino)


@role_required(T)
@require_POST
def asistencia_propia_marcar(request, pk):
    a = get_object_or_404(Asistencia.objects.select_related('jornada'), pk=pk)
    # No se acepta hora ni trabajador del cliente. Ambos provienen del servidor/sesión.
    return ejecutar(request, lambda:services.marcar_propia(request.user,a,request.POST.get('accion')), 'mi_asistencia')


@role_required(A, J)
def comparativa_temporadas(request):
    form = forms.ComparativaForm(request.GET if request.GET else None, actor=request.user)
    datos = {}
    if form.is_bound and form.is_valid():
        datos = reporting.comparar_temporadas(request.user, form.cleaned_data)
    return render(request, 'core/comparativa.html', {'form':form, **datos})


@role_required(J)
def jornada_observaciones(request, pk):
    j = get_object_or_404(Jornada.objects.select_related('temporada'), pk=pk)
    services.autorizar_jornada(request.user, j, escritura=True)
    form = forms.ObservacionesForm(request.POST if request.method == 'POST' else None,
                                   initial={'observaciones': j.observaciones})
    if request.method == 'POST' and form.is_valid():
        try:
            services.editar_observaciones(request.user, j, form.cleaned_data['observaciones'])
            messages.success(request, 'Observaciones actualizadas y registradas en auditoría.')
            return redirect(reverse('cierre') + f'?jornada={j.pk}')
        except ValidationError as exc:
            error_form(form, exc)
    return render(request, 'core/form.html', {'form': form, 'titulo': 'Observaciones de la jornada', 'volver': 'cierre',
                   'descripcion': f'{j}. Puedes editarlas mientras la jornada y la temporada estén abiertas.', 'bloqueado': not j.editable})
