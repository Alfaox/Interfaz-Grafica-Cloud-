"""Datos ficticios para explorar las interfaces; nunca reemplaza registros existentes."""
from calendar import monthrange
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from getpass import getpass
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from core import services
from core.models import (Collera, Cuadrilla, Cuartel, Cultivo, Huerto,
                         Jornada, Pesaje, Predio, Temporada, User)


class Command(BaseCommand):
    help = 'Carga una operación agrícola ficticia y dos temporadas, sin borrar ni duplicar registros.'

    def add_arguments(self, parser):
        parser.add_argument('--ask-password', action='store_true', help='Pide una contraseña de demostración sin mostrarla ni ponerla en el historial.')
        parser.add_argument('--password', default='AgroKODIT2026!', help='Contraseña solo para cuentas nuevas de demostración.')

    @transaction.atomic
    def handle(self, *args, **options):
        self.creados = Counter()
        self.password = options['password']
        if options['ask_password']:
            self.password = getpass('Contraseña para las cuentas demo nuevas (mínimo 14 caracteres): ')
            confirmacion = getpass('Repite la contraseña: ')
            if self.password != confirmacion or len(self.password) < 14:
                raise CommandError('Las contraseñas deben coincidir y tener al menos 14 caracteres.')
            try:
                validate_password(self.password)
            except ValidationError as exc:
                raise CommandError(' '.join(exc.messages)) from exc
        elif getattr(settings, 'REQUIRE_DEMO_PASSWORD', False):
            raise CommandError('En el sitio publicado utiliza --ask-password para elegir una clave privada antes de crear cuentas demo.')
        hoy = timezone.localdate()
        admin = self.usuario('admin', 'Ana', 'Administradora', User.Rol.ADMIN)
        jefe = self.usuario('jefe', 'Jorge', 'Jefe de Cuadrilla', User.Rol.JEFE)
        trabajador = self.usuario('trabajador', 'Tomás', 'Trabajador', User.Rol.TRABAJADOR)
        # No incorporar una cuenta que ya esté trabajando en una collera ajena a la demo.
        if Collera.objects.filter(Q(trabajador_uno=trabajador) | Q(trabajador_dos=trabajador), activa=True).exclude(nombre__startswith='DEMO ·').exists():
            trabajador = self.usuario('demo_tomas', 'Tomás', 'Rojas', User.Rol.TRABAJADOR)
        carolina = self.usuario('demo_carolina', 'Carolina', 'Soto', User.Rol.JEFE)
        felipe = self.usuario('demo_felipe', 'Felipe', 'Castro', User.Rol.JEFE)
        personas = [trabajador]
        nombres = [('diego','Diego','Pérez'),('valentina','Valentina','Silva'),('camila','Camila','Torres'),
                   ('benjamin','Benjamín','Díaz'),('matias','Matías','González'),('antonia','Antonia','Reyes'),
                   ('javiera','Javiera','López'),('nicolas','Nicolás','Vega'),('catalina','Catalina','Flores'),
                   ('sebastian','Sebastián','Morales'),('fernanda','Fernanda','Riquelme')]
        for username, nombre, apellido in nombres:
            personas.append(self.usuario('demo_'+username, nombre, apellido, User.Rol.TRABAJADOR))
        self.usuario('demo_disponible_1', 'Martina', 'Fuentes', User.Rol.TRABAJADOR)
        self.usuario('demo_disponible_2', 'Vicente', 'Navarro', User.Rol.TRABAJADOR)
        cerezas = self.objeto(Cultivo, {'nombre':'DEMO · Cerezas'})
        manzanas = self.objeto(Cultivo, {'nombre':'DEMO · Manzanas'})
        predios = [self.objeto(Predio, {'codigo':'DEMO-PR-01'}, nombre='DEMO · Los Aromos', ubicacion='Curicó, Región del Maule'),
                   self.objeto(Predio, {'codigo':'DEMO-PR-02'}, nombre='DEMO · Santa Elena', ubicacion='Teno, Región del Maule')]
        cuarteles = []
        for i, predio in enumerate(predios):
            for k, cultivo in enumerate([cerezas, manzanas]):
                huerto = self.objeto(Huerto, {'predio':predio,'codigo':f'DEMO-HU-{k+1:02}'}, nombre=f'Huerto {"Los Cerezos" if k==0 else "El Molino"}')
                cuarteles.append(self.objeto(Cuartel, {'huerto':huerto,'codigo':f'DEMO-C{i+1}{k+1}'},
                    nombre=f'Cuartel {"A" if i==0 else "B"}-{k+1:02}', cultivo=cultivo, superficie=Decimal('8.50')+i+k))
        equipos = []
        for i, (nombre,responsable) in enumerate([('Norte',jefe),('Sur',carolina),('Oriente',felipe)]):
            equipo = self.objeto(Cuadrilla, {'nombre':f'DEMO · Cuadrilla {nombre}'}, jefe=responsable)
            equipos.append(equipo)
            for k in range(2):
                nombre_collera = f'DEMO · Collera {i*2+k+1:02}'
                if not Collera.objects.filter(nombre=nombre_collera).exists():
                    try:
                        services.formar_collera(admin, {'nombre':nombre_collera,'cuadrilla':equipo,
                            'trabajador_uno':personas[i*4+k*2],'trabajador_dos':personas[i*4+k*2+1]})
                    except ValidationError as exc:
                        raise CommandError('No se puede formar la collera demo sin alterar asignaciones existentes: '+' '.join(exc.messages)) from exc
                    self.creados['Collera'] += 1
        self.objeto(Cuadrilla, {'nombre':'DEMO · Cuadrilla de apoyo'}, jefe=carolina)
        for anio in [hoy.year-1, hoy.year]:
            temporada = self.objeto(Temporada, {'nombre':f'DEMO · Temporada {anio}'}, inicio=date(anio,1,1), fin=date(anio,12,31))
            if not temporada.activa:
                continue  # No reabrir temporadas que ya fueron cerradas o modificadas.
            fechas = {date(anio,mes,15) for mes in range(1,13) if date(anio,mes,15)<= (hoy if anio==hoy.year else date(anio,12,31))}
            for offset in range(7):
                dia = hoy-timedelta(days=offset)
                if dia.year == hoy.year:
                    fechas.add(dia.replace(year=anio, day=min(dia.day,monthrange(anio,dia.month)[1])) if anio!=hoy.year else dia)
            for fecha in sorted(fechas):
                for i, equipo in enumerate(equipos):
                    if Jornada.objects.filter(cuadrilla=equipo,fecha=fecha).exists():
                        continue  # No completar ni alterar una jornada ya existente.
                    if not equipo.colleras.filter(activa=True).exists():
                        continue
                    datos = {'cuadrilla':equipo,'temporada':temporada,'cuartel':cuarteles[[0,2,1][i]],'fecha':fecha,
                             'hora_inicio':time(8), 'labor':'Cosecha', 'observaciones':'Datos ficticios de demostración.',
                             'autogestion_habilitada':fecha==hoy}
                    try:
                        jornada = services.abrir_jornada(equipo.jefe, datos)
                    except ValidationError as exc:
                        raise CommandError('No se pudo crear una jornada demo: '+' '.join(exc.messages)) from exc
                    self.creados['Jornada'] += 1
                    self.creados['Asistencia'] += jornada.asistencias.count()
                    for indice, participacion in enumerate(jornada.participaciones.select_related('collera')):
                        for turno in range(2):
                            base = 11500 + i*1600 + indice*2100 + turno*1400 + (fecha.toordinal()%11)*575
                            if anio==hoy.year:
                                base = round(base*1.16)
                            kilos = Decimal(base)/100
                            merma = (kilos * Decimal('0.012')).quantize(Decimal('0.01'))
                            calidad = ['EXPORTACION','NACIONAL','INDUSTRIAL'][(i+indice+turno)%3]
                            pesaje = services.guardar_pesaje(equipo.jefe,jornada,{'participacion':participacion,'kilos':kilos,
                                'merma':merma,'motivo_merma':'Fruta dañada · dato de ejemplo','calidad':calidad})
                            instante = timezone.make_aware(datetime.combine(fecha,time(10+turno*3,15+i*5)))
                            Pesaje.objects.filter(pk=pesaje.pk).update(creado=instante)
                            self.creados['Pesaje'] += 1
                    for indice, asistencia in enumerate(jornada.asistencias.all().order_by('pk')):
                        # La cuenta principal puede probar su marcaje propio hoy desde cero.
                        if fecha==hoy and asistencia.trabajador_id==trabajador.pk:
                            continue
                        if fecha!=hoy and (fecha.day+i+indice)%13==0:
                            asistencia.ausente=True
                        else:
                            asistencia.entrada=time(8,18 if (indice+fecha.day)%5==0 else 0)
                            asistencia.salida=time(17,0) if fecha<hoy else None
                        asistencia.validada=fecha<hoy
                        asistencia.full_clean()
                        asistencia.save()
                    if fecha<hoy:
                        services.cerrar_jornada(equipo.jefe,jornada)
                        Jornada.objects.filter(pk=jornada.pk).update(cerrada_en=timezone.make_aware(datetime.combine(fecha,time(18))))
            if anio<hoy.year:
                services.cerrar_temporada(admin,temporada)
        if sum(self.creados.values()):
            services.auditar(admin,'DEMO_CARGADA','Operación ficticia: '+', '.join(f'{n} {modelo}' for modelo,n in self.creados.items()))
        self.stdout.write(self.style.SUCCESS('Datos demo disponibles. No se reemplazaron usuarios, claves ni registros existentes.'))
        self.stdout.write('Nuevos: '+(', '.join(f'{modelo}: {n}' for modelo,n in self.creados.items()) or 'ninguno; la carga ya estaba realizada.'))
        self.stdout.write('Cuentas principales: admin, jefe, trabajador. Sus contraseñas existentes se conservan.')
        self.stdout.write('Nuevos jefes: demo_carolina y demo_felipe. Contraseña: la indicada con --password o la clave demo del README.')

    def objeto(self, modelo, lookup, **defaults):
        obj, creado = modelo.objects.get_or_create(**lookup, defaults=defaults)
        if creado:
            self.creados[modelo.__name__] += 1
        return obj

    def usuario(self, username, nombre, apellido, rol):
        obj, creado = User.objects.get_or_create(username=username, defaults={'first_name':nombre,'last_name':apellido,'rol':rol})
        if creado:
            obj.set_password(self.password)
            obj.save(update_fields=['password'])
            self.creados['User'] += 1
        elif obj.rol!=rol or not obj.is_active:
            raise CommandError(f'La cuenta {username} tiene otro perfil o está inactiva. No se alteró: revisa su configuración antes de cargar datos demo.')
        return obj
