#!/usr/bin/env python3
"""Carga local reproducible sobre una COPIA temporal de SQLite, sin tráfico externo.

Usa el cliente HTTP interno de Django (middleware y plantillas incluidos), no una
red real, navegador, servidor WSGI ni infraestructura de producción.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import time as hora, timedelta
from decimal import Decimal
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile
from threading import Barrier
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


def porcentaje(valores, fraccion):
    return round(sorted(valores)[max(0, math.ceil(len(valores)*fraccion)-1)], 2) if valores else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--requests',type=int,default=80)
    parser.add_argument('--extra-pesajes',type=int,default=10000)
    parser.add_argument('--output',default='docs/rendimiento_resultado.json')
    args=parser.parse_args()
    if not 2<=args.workers<=32 or not 8<=args.requests<=2000 or not 0<=args.extra_pesajes<=100000:
        parser.error('Rangos: workers 2–32, requests 8–2000, extra-pesajes 0–100000.')
    modulo=importlib.import_module(os.environ['DJANGO_SETTINGS_MODULE'])
    original=modulo.DATABASES['default']
    if original['ENGINE']!='django.db.backends.sqlite3':
        parser.error('Esta prueba aislada admite solo SQLite. No ejecuta escrituras en MySQL ni en la base original.')
    archivo=Path(original['NAME']).resolve()
    if not archivo.is_file():
        parser.error('Ejecuta primero las migraciones locales; falta la base SQLite.')
    huella_antes=hashlib.sha256(archivo.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='agrokodit-carga-') as temporal:
        copia=Path(temporal)/'pruebas.sqlite3'
        with sqlite3.connect(archivo.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(copia) as dst:
            src.backup(dst)
        from django.conf import settings
        settings.DATABASES={'default':{**original,'NAME':str(copia),'CONN_MAX_AGE':0}}
        settings.ALLOWED_HOSTS=['localhost','127.0.0.1','testserver']
        settings.DEBUG=False
        settings.SECURE_SSL_REDIRECT=False
        import django
        django.setup()
        from django.core.exceptions import ValidationError
        from django.db import connections, connection
        from django.test import Client
        from django.test.utils import CaptureQueriesContext
        from django.urls import reverse
        from django.utils import timezone
        from core import services
        from core.models import Asistencia, AuditLog, Collera, Cuadrilla, Cuartel, Cultivo, Huerto, Jornada, Pesaje, Predio, Temporada, User
        hoy=timezone.localdate()
        def usuario(nombre,rol):
            u=User(username='_carga_'+nombre,rol=rol)
            u.set_unusable_password();u.save();return u
        admin=usuario('admin','ADMIN');jefe=usuario('jefe','JEFE')
        uno=usuario('uno','TRABAJADOR');dos=usuario('dos','TRABAJADOR')
        predio=Predio.objects.create(nombre='_CARGA Predio',codigo='_CARGA-P',ubicacion='Prueba aislada')
        huerto=Huerto.objects.create(nombre='_CARGA Huerto',codigo='_CARGA-H',predio=predio)
        cultivo=Cultivo.objects.create(nombre='_CARGA Cultivo')
        cuartel=Cuartel.objects.create(nombre='_CARGA Cuartel',codigo='_CARGA-C',huerto=huerto,cultivo=cultivo,superficie=1)
        temporada=Temporada.objects.create(nombre='_CARGA Temporada',inicio=hoy-timedelta(days=30),fin=hoy+timedelta(days=30))
        equipo=Cuadrilla.objects.create(nombre='_CARGA Equipo',jefe=jefe)
        collera=services.formar_collera(admin,{'nombre':'_CARGA Collera','cuadrilla':equipo,'trabajador_uno':uno,'trabajador_dos':dos})
        trabajadores_extra=[]
        for i in range(4):
            a=usuario(f'extra_{i}_a','TRABAJADOR');b=usuario(f'extra_{i}_b','TRABAJADOR')
            trabajadores_extra.extend([a.pk,b.pk])
            services.formar_collera(admin,{'nombre':f'_CARGA Collera extra {i}', 'cuadrilla':equipo,
                                          'trabajador_uno':a,'trabajador_dos':b})
        j=services.abrir_jornada(jefe,{'cuadrilla':equipo,'temporada':temporada,'cuartel':cuartel,'fecha':hoy,'hora_inicio':hora(8),'labor':'Carga local','observaciones':''})
        p=j.participaciones.order_by('pk').first()
        Pesaje.objects.bulk_create([Pesaje(participacion=p,responsable=jefe,kilos=Decimal('1.25'),merma=0,calidad='NACIONAL') for _ in range(args.extra_pesajes)],batch_size=500)
        total_carga=Pesaje.objects.count()
        cliente=Client(HTTP_HOST='localhost');cliente.force_login(admin)
        cookies=dict((k,v.value) for k,v in cliente.cookies.items())
        perfiles={}
        for nombre in ['home','reportes']:
            with CaptureQueriesContext(connection) as consultas:
                comienzo=perf_counter();respuesta=cliente.get(reverse(nombre));duracion=(perf_counter()-comienzo)*1000
            perfiles[nombre]={'status':respuesta.status_code,'consultas_sql':len(consultas),'ms':round(duracion,2)}

        def grupo(nombre,funciones):
            barrera=Barrier(min(args.workers,len(funciones)))
            def tarea(indice,funcion):
                connections.close_all()
                if indice<args.workers:
                    barrera.wait(timeout=20)
                t=perf_counter()
                try:
                    funcion()
                    return {'estado':'aceptada','ms':(perf_counter()-t)*1000}
                except ValidationError:
                    return {'estado':'rechazada_validacion','ms':(perf_counter()-t)*1000}
                except Exception as exc:
                    return {'estado':'error','tipo':type(exc).__name__,'detalle':str(exc)[:160],'ms':(perf_counter()-t)*1000}
                finally:
                    connections.close_all()
            t=perf_counter()
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futuros=[pool.submit(tarea,i,f) for i,f in enumerate(funciones)]
                resultados=[f.result(timeout=60) for f in futuros]
            segundos=perf_counter()-t
            tiempos=[r['ms'] for r in resultados]
            return {'escenario':nombre,'operaciones':len(resultados),'estados':dict(Counter(r['estado'] for r in resultados)),
                    'errores':[r for r in resultados if r['estado']=='error'][:8], 'mediana_ms':porcentaje(tiempos,.5),
                    'p95_ms':porcentaje(tiempos,.95),'max_ms':round(max(tiempos),2),'duracion_s':round(segundos,3),
                    'operaciones_por_s':round(len(resultados)/segundos,2)}

        resultados=[]
        def lectura():
            cli=Client(HTTP_HOST='localhost')
            for clave,valor in cookies.items():
                cli.cookies[clave]=valor
            response=cli.get(reverse('reportes'))
            if response.status_code!=200:
                raise RuntimeError(f'HTTP {response.status_code}')
        resultados.append(grupo('Reportes concurrentes, con middleware y plantillas', [lectura]*args.requests))
        def crear_pesaje():
            services.guardar_pesaje(User.objects.get(pk=jefe.pk),Jornada.objects.get(pk=j.pk),
                {'participacion':p,'kilos':Decimal('2.50'),'merma':Decimal('0'),'motivo_merma':'','calidad':'NACIONAL'})
        antes=Pesaje.objects.filter(participacion=p).count()
        escritura=grupo('Pesajes simultáneos en la misma jornada',[crear_pesaje]*args.workers)
        escritura['persistidos']=Pesaje.objects.filter(participacion=p).count()-antes
        escritura['integridad']=escritura['persistidos']==escritura['estados'].get('aceptada',0)
        resultados.append(escritura)
        def marcar_distinta(pk):
            def operacion():
                services.marcar_asistencia(User.objects.get(pk=jefe.pk),Asistencia.objects.select_related('jornada').get(pk=pk),'entrada',hora(8))
            return operacion
        marcas_ids=list(Asistencia.objects.filter(jornada=j,trabajador_id__in=trabajadores_extra).values_list('pk',flat=True))
        distintas=grupo('Entradas de ocho trabajadores diferentes',[marcar_distinta(pk) for pk in marcas_ids])
        distintas['persistidas']=Asistencia.objects.filter(pk__in=marcas_ids,entrada__isnull=False).count()
        distintas['integridad']=distintas['persistidas']==len(marcas_ids)==distintas['estados'].get('aceptada',0)
        resultados.append(distintas)
        libre_uno=usuario('libre_uno','TRABAJADOR');libre_dos=usuario('libre_dos','TRABAJADOR')
        def formar(indice):
            def operacion():
                services.formar_collera(User.objects.get(pk=admin.pk),{'nombre':f'_CARGA Rival {indice}',
                    'cuadrilla':equipo,'trabajador_uno':libre_uno,'trabajador_dos':libre_dos})
            return operacion
        colleras=grupo('Creación simultánea de colleras con los mismos integrantes',[formar(i) for i in range(args.workers)])
        colleras['integridad']=Collera.objects.filter(trabajador_uno=libre_uno,activa=True).count()==1 and colleras['estados'].get('aceptada',0)==1
        resultados.append(colleras)
        asistencia=Asistencia.objects.get(jornada=j,trabajador=uno)
        def marcar():
            services.marcar_asistencia(User.objects.get(pk=jefe.pk),Asistencia.objects.select_related('jornada').get(pk=asistencia.pk),'entrada',hora(8))
        marcas=grupo('Misma entrada solicitada simultáneamente',[marcar]*args.workers)
        marcas['integridad']=marcas['estados'].get('aceptada',0)==1 and AuditLog.objects.filter(accion='ASISTENCIA_ENTRADA',detalle=f'{uno.username} · jornada {j.pk}').count()==1
        resultados.append(marcas)
        def cerrar():
            services.cerrar_jornada(User.objects.get(pk=jefe.pk),Jornada.objects.get(pk=j.pk))
        antes=Pesaje.objects.filter(participacion=p).count()
        carrera=grupo('Cierre de jornada simultáneo con pesajes',[cerrar]+[crear_pesaje]*(args.workers-1))
        j.refresh_from_db();carrera['jornada_cerrada']=j.cerrada
        try:
            crear_pesaje();carrera['rechaza_escritura_posterior']=False
        except ValidationError:
            carrera['rechaza_escritura_posterior']=True
        # Si el cierre fue serializado, ningún pesaje aceptado puede tener auditoría posterior al cierre.
        cierre_log=AuditLog.objects.filter(accion='JORNADA_CERRADA',detalle=str(j)).first()
        if cierre_log:
            carrera['sin_escrituras_despues_cierre']=not AuditLog.objects.filter(accion='PESAJE_CREADO',pk__gt=cierre_log.pk,detalle__startswith='Pesaje ').exists()
        else:
            carrera['sin_escrituras_despues_cierre']=False
        carrera['integridad']=all(carrera.get(k) for k in ['jornada_cerrada','rechaza_escritura_posterior','sin_escrituras_despues_cierre'])
        resultados.append(carrera)
        conexiones_opciones=connection.settings_dict.get('OPTIONS',{})
        correcto=all(not r['estados'].get('error') and r.get('integridad',True) for r in resultados)
        connections.close_all()
        salida={'ejecutado_utc':timezone.now().isoformat(),'python':platform.python_version(),'django':django.get_version(),
                'sistema':platform.system()+' '+platform.machine(),'motor':'SQLite '+sqlite3.sqlite_version,
                'modo_transaccion':conexiones_opciones.get('transaction_mode','DEFERRED'),'timeout_sqlite_s':conexiones_opciones.get('timeout',5),
                'aislamiento':'Copia temporal del archivo SQLite; sin escrituras en el original.',
                'base_original_sin_cambios':huella_antes==hashlib.sha256(archivo.read_bytes()).hexdigest(),
                'pesajes_en_copia':total_carga,'concurrencia':args.workers,'perfil_rutas':perfiles,'escenarios':resultados,
                'sin_errores_y_con_integridad':correcto,
                'limites':['Las lecturas usan el cliente Django interno; las escrituras concurrentes llaman a servicios, sin red ni navegador.',
                           'Un equipo local y una copia SQLite. No certifica MySQL ni disponibilidad cloud.',
                           'Las solicitudes repetidas de asistencia deben ser rechazadas por validación.',
                           'No se definió un SLA: los tiempos son mediciones, no una garantía de capacidad.']}
        destino=Path(args.output).resolve();destino.parent.mkdir(parents=True,exist_ok=True)
        destino.write_text(json.dumps(salida,ensure_ascii=False,indent=2)+'\n')
        for r in resultados:
            print(f"{r['escenario']}: {r['estados']}, p95={r['p95_ms']} ms, integridad={r.get('integridad','no aplica')}")
        print('Base original sin cambios:',salida['base_original_sin_cambios'])
        print('Informe:',destino)
    return 0 if correcto else 1


if __name__=='__main__':
    raise SystemExit(main())
