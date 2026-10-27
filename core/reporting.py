"""Consultas consolidadas con el mismo ámbito para pantalla y exportación."""
from datetime import timedelta
from decimal import Decimal
from django.db.models import Count, Sum
from django.utils import timezone
from .services import pesajes_para


def filtrar(actor, datos):
    qs = pesajes_para(actor)
    for campo, lookup in [('desde', 'participacion__jornada__fecha__gte'), ('hasta', 'participacion__jornada__fecha__lte'),
                          ('predio', 'participacion__jornada__cuartel__huerto__predio'), ('cuartel', 'participacion__jornada__cuartel')]:
        if datos.get(campo):
            qs = qs.filter(**{lookup: datos[campo]})
    return qs


def resumen(qs, hasta=None):
    totales = qs.aggregate(kilos=Sum('kilos'), merma=Sum('merma'), registros=Count('pk'), colleras=Count('participacion__collera', distinct=True))
    totales['kilos'] = totales['kilos'] or Decimal('0')
    totales['merma'] = totales['merma'] or Decimal('0')
    ranking = list(qs.order_by().values('participacion__collera__nombre').annotate(kilos=Sum('kilos')).order_by('-kilos', 'participacion__collera__nombre'))
    mayor = max((x['kilos'] for x in ranking), default=1)
    for fila in ranking:
        fila['porcentaje'] = int(fila['kilos'] / mayor * 100)
    fin = hasta or timezone.localdate()
    inicio = fin - timedelta(days=6)
    por_dia = dict(qs.filter(participacion__jornada__fecha__range=(inicio, fin)).order_by().values('participacion__jornada__fecha').annotate(total=Sum('kilos')).values_list('participacion__jornada__fecha', 'total'))
    maximo = max(por_dia.values(), default=1) or 1
    grafico = []
    for i in range(7):
        fecha = inicio + timedelta(days=i)
        kilos = por_dia.get(fecha, Decimal('0'))
        grafico.append({'fecha': fecha, 'kilos': kilos, 'altura': int(kilos / maximo * 92)})
    return {'totales': totales, 'ranking': ranking, 'grafico': grafico, 'tiene_datos': bool(totales['registros'])}


def comparar_temporadas(actor, datos):
    """Mismas métricas y filtros para ambas temporadas, sin multiplicar joins."""
    from .models import Asistencia
    from .services import jornadas_para
    temporadas = [datos['temporada_base'], datos['temporada_comparada']]
    filtros = {}
    if datos.get('predio'):
        filtros['cuartel__huerto__predio'] = datos['predio']
    if datos.get('cultivo'):
        filtros['cuartel__cultivo'] = datos['cultivo']
    grupos = {}
    tarjetas, series = [], []
    for indice, temporada in enumerate(temporadas):
        jornadas = jornadas_para(actor).filter(temporada=temporada, **filtros)
        qs = pesajes_para(actor).filter(participacion__jornada__in=jornadas)
        resumen_temporada = resumen(qs)
        asistencias = Asistencia.objects.filter(jornada__in=jornadas).select_related('jornada')
        tarjetas.append({'temporada': temporada, 'totales': resumen_temporada['totales'],
                         'jornadas': jornadas.count(), 'horas': sum((a.horas for a in asistencias), Decimal('0')),
                         'presentes': asistencias.filter(entrada__isnull=False).count()})
        agrupado = qs.order_by().values('participacion__jornada__cuartel__huerto__predio__nombre',
                                       'participacion__jornada__cuartel__cultivo__nombre').annotate(kilos=Sum('kilos'), merma=Sum('merma'))
        for registro in agrupado:
            clave = (registro['participacion__jornada__cuartel__huerto__predio__nombre'],
                     registro['participacion__jornada__cuartel__cultivo__nombre'])
            fila = grupos.setdefault(clave, {'predio': clave[0], 'cultivo': clave[1], 'base': Decimal('0'), 'comparada': Decimal('0'),
                                             'merma_base': Decimal('0'), 'merma_comparada': Decimal('0')})
            fila['base' if indice == 0 else 'comparada'] = registro['kilos']
            fila['merma_base' if indice == 0 else 'merma_comparada'] = registro['merma']
        dias = qs.order_by().values('participacion__jornada__fecha').annotate(kilos=Sum('kilos'))
        series.append([((r['participacion__jornada__fecha']-temporada.inicio).days, r['kilos']) for r in dias])
    base, comparada = [t['totales']['kilos'] for t in tarjetas]
    diferencia = comparada-base
    variacion = diferencia/base*100 if base else None
    for fila in grupos.values():
        fila['diferencia'] = fila['comparada']-fila['base']
        fila['variacion'] = fila['diferencia']/fila['base']*100 if fila['base'] else None
    max_dias = max((t.fin-t.inicio).days for t in temporadas)
    max_kilos = max(base, comparada, Decimal('1'))
    puntos = []
    for dia in sorted({round(max_dias*i/5) for i in range(6)}):
        valores = [sum((kg for d,kg in serie if d<=dia),Decimal('0')) for serie in series]
        puntos.append({'dia':dia+1,'base':valores[0],'comparada':valores[1],
                       'altura_base':int(valores[0]/max_kilos*92),'altura_comparada':int(valores[1]/max_kilos*92)})
    return {'tarjetas':tarjetas,'comparativa_filas':sorted(grupos.values(), key=lambda f:(f['predio'],f['cultivo'])),
            'diferencia':diferencia,'variacion':variacion,'puntos':puntos,'hay_registros':bool(base or comparada)}


def ranking_trabajadores(qs):
    """Reparto matemático 50/50 de pesajes filtrados; no es una medición personal.

    Se agrega por FK de integrante y collera en dos consultas, evitando cargar
    cada pesaje y preservando los miembros históricos de colleras desarmadas.
    """
    personas = {}
    for integrante in ['trabajador_uno', 'trabajador_dos']:
        prefijo = f'participacion__collera__{integrante}'
        filas = qs.order_by().values(f'{prefijo}__id', f'{prefijo}__username', f'{prefijo}__first_name',
                                    f'{prefijo}__last_name', 'participacion__collera_id').annotate(kilos=Sum('kilos'), pesajes=Count('pk'))
        for fila in filas:
            pk = fila[f'{prefijo}__id']
            nombre = f"{fila[f'{prefijo}__first_name']} {fila[f'{prefijo}__last_name']}".strip() or fila[f'{prefijo}__username']
            persona = personas.setdefault(pk, {'id':pk, 'nombre':nombre, 'username':fila[f'{prefijo}__username'],
                                               'kilos_colleras':Decimal('0'), 'pesajes':0, 'colleras':set()})
            persona['kilos_colleras'] += fila['kilos']
            persona['pesajes'] += fila['pesajes']
            persona['colleras'].add(fila['participacion__collera_id'])
    for persona in personas.values():
        persona['kilos_estimados'] = persona['kilos_colleras'] / Decimal('2')
        persona['colleras'] = len(persona['colleras'])
    filas = sorted(personas.values(), key=lambda p:(-p['kilos_estimados'],p['nombre'].casefold(),p['id']))
    puesto = 0
    anterior = None
    for indice, persona in enumerate(filas, start=1):
        if persona['kilos_estimados'] != anterior:
            puesto = indice
        persona['puesto'] = puesto
        anterior = persona['kilos_estimados']
    return filas
