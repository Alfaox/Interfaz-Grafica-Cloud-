from django.test import TestCase
from django.urls import reverse

from .models import AuditLog, User


class RolesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        for u, r in (("a", "ADMIN"), ("j", "JEFE"), ("t", "TRABAJADOR")):
            User.objects.create_user(u, password="Clave-segura-123", rol=r)

    def entrar(self, u):
        self.client.login(username=u, password="Clave-segura-123")

    def test_anonimo_va_a_login(self):
        r = self.client.get(reverse("home"))
        self.assertRedirects(r, "/login/?next=/")

    def test_login_ok_y_auditado(self):
        r = self.client.post(reverse("login"), {"username": "a", "password": "Clave-segura-123"})
        self.assertRedirects(r, reverse("home"))
        self.assertTrue(AuditLog.objects.filter(accion="LOGIN").exists())

    def test_login_fallido_auditado(self):
        self.client.post(reverse("login"), {"username": "a", "password": "mala"})
        self.assertTrue(AuditLog.objects.filter(accion="LOGIN_FALLIDO").exists())

    def test_menu_distinto_por_rol(self):
        esperado = {"a": ("Usuarios y roles", "Auditoría"), "j": ("Registrar kilos", "Cerrar jornada"), "t": ("Mi asistencia", "Mi producción")}
        for u, propios in esperado.items():
            self.entrar(u)
            html = self.client.get(reverse("home")).content.decode()
            for etiqueta in propios:
                self.assertIn(etiqueta, html)
            for otro, ajenos in esperado.items():
                if otro != u:
                    for etiqueta in ajenos:
                        self.assertNotIn(etiqueta, html)
            self.client.logout()

    def test_rol_sin_permiso_recibe_403(self):
        casos = {"t": ["usuarios", "kilos", "reportes"], "j": ["usuarios", "auditoria", "mi_asistencia"]}
        for u, urls in casos.items():
            self.entrar(u)
            for n in urls:
                self.assertEqual(self.client.get(reverse(n)).status_code, 403, (u, n))
            self.client.logout()

    def test_admin_crea_usuario(self):
        self.entrar("a")
        r = self.client.post(reverse("usuario_nuevo"), {
            "username": "nuevo", "rol": "JEFE", "password1": "Otra-clave-Larga-77", "password2": "Otra-clave-Larga-77"})
        self.assertRedirects(r, reverse("usuarios"))
        self.assertEqual(User.objects.get(username="nuevo").rol, "JEFE")

    def test_hash_argon2(self):
        self.assertTrue(User.objects.get(username="a").password.startswith("argon2"))


from datetime import time, timedelta
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.utils import timezone
from . import services
from .models import (Asistencia, Collera, Cuadrilla, Cuartel, Cultivo, Huerto,
                     Jornada, Participacion, Pesaje, Predio, Temporada)


class OperacionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user('admin-op', password='Clave-segura-123', rol='ADMIN')
        cls.jefe = User.objects.create_user('jefe-op', password='Clave-segura-123', rol='JEFE')
        cls.otro_jefe = User.objects.create_user('otro-jefe', password='Clave-segura-123', rol='JEFE')
        cls.uno = User.objects.create_user('uno', password='Clave-segura-123', rol='TRABAJADOR')
        cls.dos = User.objects.create_user('dos', password='Clave-segura-123', rol='TRABAJADOR')
        cls.ajeno = User.objects.create_user('ajeno', password='Clave-segura-123', rol='TRABAJADOR')
        p = Predio.objects.create(nombre='Los Aromos', codigo='P1', ubicacion='Curicó')
        h = Huerto.objects.create(predio=p, nombre='Cerezos', codigo='H1')
        c = Cultivo.objects.create(nombre='Cerezas')
        cls.cuartel = Cuartel.objects.create(huerto=h, cultivo=c, nombre='A1', codigo='A1', superficie='8.5')
        hoy = timezone.localdate()
        cls.temporada = Temporada.objects.create(nombre='Prueba', inicio=hoy-timedelta(days=20), fin=hoy+timedelta(days=20))
        cls.equipo = Cuadrilla.objects.create(nombre='Norte', jefe=cls.jefe)
        cls.collera = services.formar_collera(cls.admin, {'nombre':'Collera 01', 'cuadrilla':cls.equipo, 'trabajador_uno':cls.uno, 'trabajador_dos':cls.dos})
        cls.jornada = services.abrir_jornada(cls.jefe, {'cuadrilla':cls.equipo, 'temporada':cls.temporada, 'cuartel':cls.cuartel,
                                                     'fecha':hoy, 'hora_inicio':time(8), 'labor':'Cosecha', 'observaciones':''})
        cls.participacion = cls.jornada.participaciones.get()
        cls.pesaje = services.guardar_pesaje(cls.jefe, cls.jornada, {'participacion':cls.participacion, 'kilos':Decimal('123.45'),
                                             'merma':Decimal('1.20'), 'motivo_merma':'Daño', 'calidad':'EXPORTACION'})

    def entrar(self, usuario):
        self.client.force_login(usuario)

    def test_reportes_muestra_datos_reales(self):
        self.entrar(self.admin)
        r = self.client.get(reverse('reportes'))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'core/reportes.html')
        self.assertEqual(r.context['totales']['kilos'], Decimal('123.45'))
        self.assertEqual(r.context['ranking'][0]['participacion__collera__nombre'], 'Collera 01')
        self.assertNotContains(r, 'Este módulo se implementará')

    def test_pantallas_por_perfil(self):
        casos = [(self.admin, ['home','usuarios','predios','cuadrilla','cierre','reportes','auditoria']),
                 (self.jefe, ['home','cuadrilla','asistencia','kilos','cierre','reportes','jornada_nueva']),
                 (self.uno, ['home','mi_asistencia','mi_produccion'])]
        for actor, nombres in casos:
            self.entrar(actor)
            for nombre in nombres:
                with self.subTest(actor=actor.username, ruta=nombre):
                    r = self.client.get(reverse(nombre))
                    self.assertEqual(r.status_code, 200)
                    self.assertNotContains(r, 'Este módulo se implementará')

    def test_pantallas_sin_datos(self):
        self.entrar(self.otro_jefe)
        for nombre in ['home','cuadrilla','asistencia','kilos','cierre','reportes']:
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200)
        self.assertEqual(self.client.get(reverse('reportes')).context['totales']['registros'], 0)

    def test_catalogos_renderizan(self):
        self.entrar(self.admin)
        for tipo in ['predio','huerto','cultivo','cuartel','temporada','cuadrilla','collera']:
            self.assertEqual(self.client.get(reverse('catalogo_nuevo', args=[tipo])).status_code, 200)

    def test_jefe_no_consulta_jornada_ajena(self):
        self.entrar(self.otro_jefe)
        for ruta in ['asistencia','kilos','cierre']:
            self.assertEqual(self.client.get(reverse(ruta), {'jornada':self.jornada.pk}).status_code, 403)
        self.assertTrue(AuditLog.objects.filter(accion='ACCESO_DENEGADO', usuario=self.otro_jefe).exists())

    def test_reportes_y_exportacion_respetan_ambito(self):
        self.entrar(self.otro_jefe)
        r = self.client.get(reverse('reportes'))
        self.assertEqual(r.context['totales']['registros'], 0)
        self.assertNotContains(r, 'Collera 01')
        self.assertEqual(self.client.get(reverse('reportes'), {'exportar':'csv'}).status_code, 403)

    def test_trabajador_no_ve_produccion_ajena(self):
        self.entrar(self.ajeno)
        r = self.client.get(reverse('mi_produccion'))
        self.assertEqual(r.context['totales']['kilos'], 0)
        self.assertNotContains(r, 'Collera 01')
        self.entrar(self.uno)
        self.assertEqual(self.client.get(reverse('mi_produccion')).context['totales']['kilos'], Decimal('123.45'))

    def test_formulario_rechaza_kilos_invalidos(self):
        self.entrar(self.jefe)
        for kilos in ['0','-12.5','35.456']:
            r = self.client.post(reverse('kilos')+f'?jornada={self.jornada.pk}', {'participacion':self.participacion.pk,
                         'kilos':kilos, 'merma':'0', 'calidad':'EXPORTACION'})
            self.assertEqual(r.status_code, 200)
            self.assertIn('kilos', r.context['form'].errors)
        self.assertEqual(Pesaje.objects.count(), 1)

    def test_guardar_pesaje_actualiza_reporte(self):
        self.entrar(self.jefe)
        r = self.client.post(reverse('kilos')+f'?jornada={self.jornada.pk}', {'participacion':self.participacion.pk,
                         'kilos':'10.25', 'merma':'0', 'calidad':'NACIONAL'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get(reverse('reportes')).context['totales']['kilos'], Decimal('133.70'))

    def test_cierre_bloquea_rutas_directas(self):
        services.cerrar_jornada(self.jefe, self.jornada)
        self.entrar(self.jefe)
        r = self.client.post(reverse('kilos')+f'?jornada={self.jornada.pk}', {'participacion':self.participacion.pk,
                         'kilos':'10', 'merma':'0', 'calidad':'NACIONAL'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context['form'].non_field_errors())
        r = self.client.post(reverse('pesaje_editar', args=[self.pesaje.pk]), {'participacion':self.participacion.pk,
                         'kilos':'99', 'merma':'0', 'calidad':'NACIONAL'})
        self.assertTrue(r.context['form'].non_field_errors())
        self.pesaje.refresh_from_db()
        self.assertEqual(self.pesaje.kilos, Decimal('123.45'))
        a = self.jornada.asistencias.get(trabajador=self.uno)
        with self.assertRaises(ValidationError):
            services.marcar_asistencia(self.jefe, a, 'entrada', time(8))

    def test_reapertura_exige_admin_y_motivo(self):
        services.cerrar_jornada(self.jefe, self.jornada)
        with self.assertRaises(PermissionDenied):
            services.reabrir_jornada(self.jefe, self.jornada, 'Corrección de pesaje')
        with self.assertRaises(ValidationError):
            services.reabrir_jornada(self.admin, self.jornada, '')
        services.reabrir_jornada(self.admin, self.jornada, 'Corrección de pesaje')
        self.jornada.refresh_from_db()
        self.assertTrue(self.jornada.editable)
        self.assertTrue(AuditLog.objects.filter(accion='JORNADA_REABIERTA').exists())

    def test_temporada_cerrada_bloquea(self):
        services.cerrar_temporada(self.admin, self.temporada)
        with self.assertRaises(ValidationError):
            services.guardar_pesaje(self.jefe, self.jornada, {'participacion':self.participacion, 'kilos':Decimal('1'),
                                              'merma':Decimal('0'), 'calidad':'NACIONAL', 'motivo_merma':''})
        with self.assertRaises(ValidationError):
            services.reabrir_jornada(self.admin, self.jornada, 'Motivo de excepción')

    def test_collera_no_duplica_integrantes(self):
        with self.assertRaises(ValidationError):
            services.formar_collera(self.admin, {'nombre':'Duplicada', 'cuadrilla':self.equipo, 'trabajador_uno':self.uno, 'trabajador_dos':self.ajeno})
        with self.assertRaises(ValidationError):
            services.formar_collera(self.admin, {'nombre':'Individual', 'cuadrilla':self.equipo, 'trabajador_uno':self.ajeno, 'trabajador_dos':self.ajeno})
        self.assertEqual(Collera.objects.count(), 1)

    def test_asistencia_cronologia_ausencia_y_horas(self):
        a = self.jornada.asistencias.get(trabajador=self.uno)
        with self.assertRaises(ValidationError):
            services.marcar_asistencia(self.jefe, a, 'salida', time(17))
        services.marcar_asistencia(self.jefe, a, 'entrada', time(8, 15))
        with self.assertRaises(ValidationError):
            services.marcar_asistencia(self.jefe, a, 'salida', time(7))
        with self.assertRaises(ValidationError):
            services.marcar_asistencia(self.jefe, a, 'ausente')
        services.marcar_asistencia(self.jefe, a, 'salida', time(17))
        a.refresh_from_db()
        self.assertEqual(a.horas, Decimal('8.75'))
        self.assertTrue(a.atraso)

    def test_exportacion_filtrada_y_segura(self):
        self.entrar(self.admin)
        r = self.client.get(reverse('reportes'), {'exportar':'csv'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('123.45', r.content.decode())
        r = self.client.get(reverse('reportes'), {'exportar':'csv', 'desde':str(timezone.localdate()+timedelta(days=1))})
        self.assertNotIn('123.45', r.content.decode())
        self.assertTrue(AuditLog.objects.filter(accion='REPORTE_EXPORTADO').exists())

    def test_fechas_invalidas_no_amplian_reporte(self):
        self.entrar(self.admin)
        for params in [{'desde':'no-fecha'}, {'desde':'2026-10-30','hasta':'2026-10-01'}]:
            r = self.client.get(reverse('reportes'), params)
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.context['form'].errors)
            self.assertEqual(r.context['totales']['registros'], 0)

    def test_operaciones_solo_post_y_csrf(self):
        self.entrar(self.jefe)
        self.assertEqual(self.client.get(reverse('jornada_cerrar', args=[self.jornada.pk])).status_code, 405)
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.jefe)
        self.assertEqual(cliente.post(reverse('jornada_cerrar', args=[self.jornada.pk]), {'confirmar':'si'}).status_code, 403)

    def test_flujo_http_apertura_asistencia_pesaje_cierre_reapertura(self):
        self.entrar(self.jefe)
        fecha = timezone.localdate() + timedelta(days=1)
        r = self.client.post(reverse('jornada_nueva'), {'cuadrilla':self.equipo.pk, 'temporada':self.temporada.pk,
                        'cuartel':self.cuartel.pk, 'fecha':str(fecha), 'hora_inicio':'08:00', 'labor':'Cosecha', 'observaciones':'Turno de prueba'})
        self.assertEqual(r.status_code, 302)
        j = Jornada.objects.get(cuadrilla=self.equipo, fecha=fecha)
        self.assertEqual(j.asistencias.count(), 2)
        a = j.asistencias.get(trabajador=self.uno)
        self.assertEqual(self.client.post(reverse('asistencia_marca', args=[a.pk]), {'accion':'entrada','hora':'08:00'}).status_code, 302)
        self.assertEqual(self.client.post(reverse('asistencia_marca', args=[a.pk]), {'accion':'salida','hora':'17:00'}).status_code, 302)
        self.assertEqual(self.client.post(reverse('asistencia_validar', args=[j.pk])).status_code, 302)
        self.assertEqual(self.client.post(reverse('kilos')+f'?jornada={j.pk}', {'participacion':j.participaciones.get().pk,
                     'kilos':'55.25','merma':'0','calidad':'EXPORTACION'}).status_code, 302)
        reporte = self.client.get(reverse('reportes'), {'desde':str(fecha),'hasta':str(fecha)})
        self.assertEqual(reporte.context['totales']['kilos'], Decimal('55.25'))
        self.assertContains(self.client.get(reverse('cierre'), {'jornada':j.pk}), '55,25')
        self.assertEqual(self.client.post(reverse('jornada_cerrar', args=[j.pk]), {'confirmar':'si'}).status_code, 302)
        j.refresh_from_db()
        self.assertTrue(j.cerrada)
        self.entrar(self.admin)
        self.assertEqual(self.client.post(reverse('jornada_reabrir', args=[j.pk]), {'motivo':'Corregir un pesaje pendiente'}).status_code, 302)
        j.refresh_from_db()
        self.assertFalse(j.cerrada)

    def datos_usuario(self, persona, **cambios):
        data = {'username':persona.username,'first_name':persona.first_name,'last_name':persona.last_name,
                'email':persona.email,'rol':persona.rol,'is_active':'on' if persona.is_active else ''}
        data.update(cambios)
        return data

    def test_editar_usuario_rol_sin_escalar_privilegios_django(self):
        self.entrar(self.admin)
        clave = self.ajeno.password
        r = self.client.post(reverse('usuario_editar',args=[self.ajeno.pk]),self.datos_usuario(self.ajeno,
                    first_name='Nuevo nombre',rol='JEFE',is_superuser='on',is_staff='on',password='texto-plano'))
        self.assertEqual(r.status_code,302)
        self.ajeno.refresh_from_db()
        self.assertEqual(self.ajeno.rol,'JEFE')
        self.assertEqual(self.ajeno.first_name,'Nuevo nombre')
        self.assertEqual(self.ajeno.password,clave)
        self.assertFalse(self.ajeno.is_superuser)
        self.assertFalse(self.ajeno.is_staff)
        self.assertTrue(AuditLog.objects.filter(accion='ROL_CAMBIADO').exists())

    def test_admin_no_se_desactiva_ni_se_quita_permisos(self):
        self.entrar(self.admin)
        for cambios in [{'rol':'TRABAJADOR'},{'is_active':''}]:
            r=self.client.post(reverse('usuario_editar',args=[self.admin.pk]),self.datos_usuario(self.admin,**cambios))
            self.assertEqual(r.status_code,200)
            self.assertTrue(r.context['form'].non_field_errors())
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.rol,'ADMIN')
        self.assertTrue(self.admin.is_active)

    def test_no_cambia_perfil_de_personas_asignadas(self):
        self.entrar(self.admin)
        for persona in [self.uno,self.jefe]:
            for cambios in [{'rol':'ADMIN'},{'is_active':''}]:
                r=self.client.post(reverse('usuario_editar',args=[persona.pk]),self.datos_usuario(persona,**cambios))
                self.assertEqual(r.status_code,200)
                self.assertTrue(r.context['form'].non_field_errors())
                persona.refresh_from_db()
                self.assertTrue(persona.is_active)
                self.assertNotEqual(persona.rol,'ADMIN')

    def test_sesion_refleja_cambio_rol_y_desactivacion(self):
        self.ajeno.rol='ADMIN';self.ajeno.save()
        anterior=Client();anterior.force_login(self.ajeno)
        self.assertEqual(anterior.get(reverse('usuarios')).status_code,200)
        self.entrar(self.admin)
        self.client.post(reverse('usuario_editar',args=[self.ajeno.pk]),self.datos_usuario(self.ajeno,rol='TRABAJADOR'))
        self.assertEqual(anterior.get(reverse('usuarios')).status_code,403)
        self.ajeno.refresh_from_db()
        self.client.post(reverse('usuario_editar',args=[self.ajeno.pk]),self.datos_usuario(self.ajeno,is_active=''))
        self.assertEqual(anterior.get(reverse('home')).status_code,302)

    def test_edicion_catalogos_get_y_permisos(self):
        items=[('predio',self.cuartel.huerto.predio),('huerto',self.cuartel.huerto),('cultivo',self.cuartel.cultivo),
               ('cuartel',self.cuartel),('temporada',self.temporada),('cuadrilla',self.equipo),('collera',self.collera)]
        self.entrar(self.admin)
        for tipo,obj in items:
            self.assertEqual(self.client.get(reverse('catalogo_editar',args=[tipo,obj.pk])).status_code,200)
        self.entrar(self.jefe)
        for tipo,obj in items:
            self.assertEqual(self.client.post(reverse('catalogo_editar',args=[tipo,obj.pk]),{}).status_code,403)
        self.assertEqual(self.client.get(reverse('usuario_editar',args=[self.ajeno.pk])).status_code,403)

    def test_editar_catalogos_conserva_identidad_y_valida_duplicados(self):
        self.entrar(self.admin)
        p=self.cuartel.huerto.predio
        r=self.client.post(reverse('catalogo_editar',args=['predio',p.pk]),{'nombre':'Los Aromos corregido','codigo':p.codigo,'ubicacion':'Curicó centro','activo':''})
        self.assertEqual(r.status_code,302)
        p.refresh_from_db();self.assertTrue(p.activo)
        self.assertEqual(p.nombre,'Los Aromos corregido')
        p2=Predio.objects.create(nombre='Otro',codigo='OT',ubicacion='Teno')
        r=self.client.post(reverse('catalogo_editar',args=['predio',p.pk]),{'nombre':p2.nombre,'codigo':p.codigo,'ubicacion':p.ubicacion})
        self.assertEqual(r.status_code,200);self.assertTrue(r.context['form'].errors)
        p.refresh_from_db();self.assertEqual(p.nombre,'Los Aromos corregido')
        self.assertTrue(AuditLog.objects.filter(accion='CATALOGO_EDITADO').exists())

    def test_catalogo_no_reubica_historial(self):
        self.entrar(self.admin)
        p2=Predio.objects.create(nombre='Otro',codigo='OT',ubicacion='Teno')
        h=self.cuartel.huerto
        r=self.client.post(reverse('catalogo_editar',args=['huerto',h.pk]),{'nombre':h.nombre,'codigo':h.codigo,'predio':p2.pk})
        self.assertTrue(r.context['form'].non_field_errors())
        h.refresh_from_db();self.assertNotEqual(h.predio_id,p2.pk)
        cultivo=Cultivo.objects.create(nombre='Manzanas')
        c=self.cuartel
        r=self.client.post(reverse('catalogo_editar',args=['cuartel',c.pk]),{'nombre':c.nombre,'codigo':c.codigo,'huerto':h.pk,'cultivo':cultivo.pk,'superficie':'10'})
        self.assertTrue(r.context['form'].non_field_errors())
        c.refresh_from_db();self.assertNotEqual(c.cultivo_id,cultivo.pk)

    def test_temporada_editada_no_excluye_jornadas_ni_reabre(self):
        self.entrar(self.admin)
        t=self.temporada
        r=self.client.post(reverse('catalogo_editar',args=['temporada',t.pk]),{'nombre':t.nombre,'inicio':str(timezone.localdate()+timedelta(days=1)),'fin':str(t.fin)})
        self.assertTrue(r.context['form'].non_field_errors())
        services.cerrar_temporada(self.admin,t)
        r=self.client.post(reverse('catalogo_editar',args=['temporada',t.pk]),{'nombre':'Nombre corregido','inicio':str(t.inicio),'fin':str(t.fin),'activa':'on'})
        self.assertEqual(r.status_code,302)
        t.refresh_from_db();self.assertFalse(t.activa)

    def test_cambio_jefe_exige_cierre_y_conserva_responsable(self):
        self.entrar(self.admin)
        datos={'nombre':self.equipo.nombre,'jefe':self.otro_jefe.pk}
        r=self.client.post(reverse('catalogo_editar',args=['cuadrilla',self.equipo.pk]),datos)
        self.assertTrue(r.context['form'].non_field_errors())
        services.cerrar_jornada(self.jefe,self.jornada)
        r=self.client.post(reverse('catalogo_editar',args=['cuadrilla',self.equipo.pk]),datos)
        self.assertEqual(r.status_code,302)
        self.jornada.refresh_from_db();self.assertEqual(self.jornada.jefe_id,self.jefe.pk)
        self.equipo.refresh_from_db();self.assertEqual(self.equipo.jefe_id,self.otro_jefe.pk)
        self.assertFalse(services.pesajes_para(self.otro_jefe).exists())

    def test_traslado_conserva_pesajes_y_asistencia_historica(self):
        destino=Cuadrilla.objects.create(nombre='Sur',jefe=self.otro_jefe)
        self.entrar(self.admin)
        r=self.client.post(reverse('collera_trasladar',args=[self.collera.pk]),{'destino':destino.pk,'motivo':'Balance de equipos'})
        self.assertEqual(r.status_code,302)
        self.collera.refresh_from_db();self.assertEqual(self.collera.cuadrilla_id,destino.pk)
        self.jornada.refresh_from_db();self.assertEqual(self.jornada.cuadrilla_id,self.equipo.pk)
        self.assertEqual(services.pesajes_para(self.jefe).count(),1)
        self.assertEqual(services.pesajes_para(self.otro_jefe).count(),0)
        datos={'cuadrilla':destino,'temporada':self.temporada,'cuartel':self.cuartel,'fecha':self.jornada.fecha,
               'hora_inicio':time(8),'labor':'Cosecha','observaciones':''}
        with self.assertRaises(ValidationError):services.abrir_jornada(self.otro_jefe,datos)
        datos['fecha']+=timedelta(days=1)
        nueva=services.abrir_jornada(self.otro_jefe,datos)
        self.assertEqual(nueva.participaciones.get().collera_id,self.collera.pk)
        self.assertEqual(nueva.asistencias.count(),2)
        self.assertTrue(AuditLog.objects.filter(accion='COLLERA_TRASLADADA').exists())

    def test_traslado_rechaza_rol_inactiva_destino_y_motivo(self):
        destino=Cuadrilla.objects.create(nombre='Sur',jefe=self.otro_jefe)
        self.entrar(self.jefe)
        self.assertEqual(self.client.post(reverse('collera_trasladar',args=[self.collera.pk]),{'destino':destino.pk,'motivo':'Balance de equipos'}).status_code,403)
        self.entrar(self.admin)
        for valores in [{'destino':self.equipo.pk,'motivo':'Balance de equipos'},{'destino':destino.pk,'motivo':''}]:
            r=self.client.post(reverse('collera_trasladar',args=[self.collera.pk]),valores)
            self.assertEqual(r.status_code,200);self.assertTrue(r.context['form'].errors)
        self.collera.activa=False;self.collera.save()
        r=self.client.post(reverse('collera_trasladar',args=[self.collera.pk]),{'destino':destino.pk,'motivo':'Balance de equipos'})
        self.assertTrue(r.context['form'].non_field_errors())

    def test_autogestion_solo_jefe_propio_configura(self):
        self.entrar(self.otro_jefe)
        self.assertEqual(self.client.post(reverse('autogestion_configurar',args=[self.jornada.pk]),{'habilitada':'on'}).status_code,403)
        self.entrar(self.jefe)
        self.assertEqual(self.client.post(reverse('autogestion_configurar',args=[self.jornada.pk]),{'habilitada':'on'}).status_code,302)
        self.jornada.refresh_from_db();self.assertTrue(self.jornada.autogestion_habilitada)
        self.assertEqual(self.client.post(reverse('autogestion_configurar',args=[self.jornada.pk]),{}).status_code,302)
        self.jornada.refresh_from_db();self.assertFalse(self.jornada.autogestion_habilitada)
        services.cerrar_jornada(self.jefe,self.jornada)
        self.client.post(reverse('autogestion_configurar',args=[self.jornada.pk]),{'habilitada':'on'})
        self.jornada.refresh_from_db();self.assertFalse(self.jornada.autogestion_habilitada)

    def test_autogestion_denegada_si_deshabilitada_o_asistencia_ajena(self):
        a=self.jornada.asistencias.get(trabajador=self.uno)
        self.entrar(self.uno)
        self.assertEqual(self.client.post(reverse('asistencia_propia_marcar',args=[a.pk]),{'accion':'entrada'}).status_code,403)
        services.configurar_autogestion(self.jefe,self.jornada,True)
        ajena=self.jornada.asistencias.get(trabajador=self.dos)
        self.assertEqual(self.client.post(reverse('asistencia_propia_marcar',args=[ajena.pk]),{'accion':'entrada'}).status_code,403)
        a.refresh_from_db();self.assertIsNone(a.entrada)

    def test_autogestion_hora_servidor_marcas_pendientes_validacion(self):
        from unittest.mock import patch
        from datetime import datetime
        services.configurar_autogestion(self.jefe,self.jornada,True)
        a=self.jornada.asistencias.get(trabajador=self.uno)
        self.entrar(self.uno)
        self.assertContains(self.client.get(reverse('mi_asistencia')),'Marcar mi entrada')
        def momento(hora):
            return datetime.combine(timezone.localdate(),time(hora,15)).replace(tzinfo=timezone.get_current_timezone())
        with patch('core.services.timezone.localtime',return_value=momento(8)):
            self.assertEqual(self.client.post(reverse('asistencia_propia_marcar',args=[a.pk]),{'accion':'entrada','hora':'01:00','trabajador':self.dos.pk}).status_code,302)
            self.client.post(reverse('asistencia_propia_marcar',args=[a.pk]),{'accion':'entrada'})
        a.refresh_from_db();self.assertEqual(a.entrada,time(8,15));self.assertFalse(a.validada)
        services.validar_asistencia(self.jefe,self.jornada)
        with patch('core.services.timezone.localtime',return_value=momento(17)):
            self.client.post(reverse('asistencia_propia_marcar',args=[a.pk]),{'accion':'salida','hora':'02:00'})
        a.refresh_from_db();self.assertEqual(a.salida,time(17,15));self.assertFalse(a.validada)
        self.assertEqual(a.horas,Decimal('9'))
        self.assertEqual(AuditLog.objects.filter(accion='ASISTENCIA_PROPIA').count(),2)
        self.assertContains(self.client.get(reverse('mi_asistencia')),'Completada')

    def test_autogestion_rechaza_ausencia_cierre_fechas_y_acciones(self):
        services.configurar_autogestion(self.jefe,self.jornada,True)
        a=self.jornada.asistencias.get(trabajador=self.uno)
        with self.assertRaises(ValidationError):services.marcar_propia(self.uno,a,'ausente')
        with self.assertRaises(ValidationError):services.marcar_propia(self.uno,a,'salida')
        a.ausente=True;a.save()
        with self.assertRaises(ValidationError):services.marcar_propia(self.uno,a,'entrada')
        a.ausente=False;a.save()
        services.cerrar_jornada(self.jefe,self.jornada)
        with self.assertRaises(ValidationError):services.marcar_propia(self.uno,a,'entrada')
        self.jornada.refresh_from_db()
        self.jornada.cerrada=False;self.jornada.fecha-=timedelta(days=1);self.jornada.save(update_fields=['cerrada','fecha'])
        a=Asistencia.objects.select_related('jornada').get(pk=a.pk)
        with self.assertRaises(ValidationError):services.marcar_propia(self.uno,a,'entrada')

    def preparar_comparacion(self):
        antigua=Temporada.objects.create(nombre='Anterior',inicio=self.temporada.inicio-timedelta(days=365),fin=self.temporada.fin-timedelta(days=365))
        j=services.abrir_jornada(self.jefe,{'cuadrilla':self.equipo,'temporada':antigua,'cuartel':self.cuartel,
               'fecha':self.jornada.fecha-timedelta(days=365),'hora_inicio':time(8),'labor':'Cosecha','observaciones':''})
        services.guardar_pesaje(self.jefe,j,{'participacion':j.participaciones.get(),'kilos':Decimal('100.00'),
                                          'merma':Decimal('2.00'),'motivo_merma':'Daño','calidad':'NACIONAL'})
        services.cerrar_temporada(self.admin,antigua)
        return antigua

    def test_comparativa_temporadas_totales_variaciones_y_grafico(self):
        antigua=self.preparar_comparacion()
        self.entrar(self.admin)
        r=self.client.get(reverse('comparativa_temporadas'),{'temporada_base':antigua.pk,'temporada_comparada':self.temporada.pk})
        self.assertEqual(r.status_code,200)
        self.assertFalse(r.context['form'].errors)
        self.assertEqual(r.context['diferencia'],Decimal('23.45'))
        self.assertEqual(r.context['variacion'],Decimal('23.45'))
        self.assertEqual(r.context['comparativa_filas'][0]['base'],Decimal('100'))
        self.assertEqual(r.context['comparativa_filas'][0]['comparada'],Decimal('123.45'))
        self.assertEqual(r.context['puntos'][-1]['base'],Decimal('100'))
        self.assertEqual(r.context['tarjetas'][0]['totales']['merma'],Decimal('2'))

    def test_comparativa_sin_datos_no_divide_por_cero(self):
        vacia=Temporada.objects.create(nombre='Vacía',inicio=self.temporada.inicio,fin=self.temporada.fin)
        self.entrar(self.admin)
        r=self.client.get(reverse('comparativa_temporadas'),{'temporada_base':vacia.pk,'temporada_comparada':self.temporada.pk})
        self.assertEqual(r.status_code,200);self.assertIsNone(r.context['variacion'])
        self.assertEqual(r.context['diferencia'],Decimal('123.45'))
        self.assertContains(r,'referencia sin kilos')

    def test_comparativa_filtros_ambito_y_temporadas_invalidas(self):
        antigua=self.preparar_comparacion()
        self.entrar(self.jefe)
        r=self.client.get(reverse('comparativa_temporadas'),{'temporada_base':antigua.pk,'temporada_comparada':self.temporada.pk,'cultivo':self.cuartel.cultivo_id,'predio':self.cuartel.huerto.predio_id})
        self.assertEqual(r.context['diferencia'],Decimal('23.45'))
        self.entrar(self.otro_jefe)
        r=self.client.get(reverse('comparativa_temporadas'),{'temporada_base':antigua.pk,'temporada_comparada':self.temporada.pk})
        self.assertTrue(r.context['form'].errors);self.assertNotIn('tarjetas',r.context)
        self.entrar(self.uno)
        self.assertEqual(self.client.get(reverse('comparativa_temporadas')).status_code,403)
        self.entrar(self.admin)
        for valores in [{'temporada_base':antigua.pk,'temporada_comparada':antigua.pk}, {'temporada_base':'abc','temporada_comparada':self.temporada.pk}]:
            r=self.client.get(reverse('comparativa_temporadas'),valores)
            self.assertTrue(r.context['form'].errors);self.assertNotIn('tarjetas',r.context)
        otro=Cultivo.objects.create(nombre='Manzanas')
        r=self.client.get(reverse('comparativa_temporadas'),{'temporada_base':antigua.pk,'temporada_comparada':self.temporada.pk,'cultivo':otro.pk})
        self.assertEqual(r.context['diferencia'],0);self.assertFalse(r.context['hay_registros'])

    def test_nuevas_operaciones_solo_post_y_csrf(self):
        self.entrar(self.uno)
        a=self.jornada.asistencias.get(trabajador=self.uno)
        self.assertEqual(self.client.get(reverse('asistencia_propia_marcar',args=[a.pk])).status_code,405)
        cliente=Client(enforce_csrf_checks=True);cliente.force_login(self.uno)
        self.assertEqual(cliente.post(reverse('asistencia_propia_marcar',args=[a.pk]),{'accion':'entrada'}).status_code,403)
        self.entrar(self.jefe)
        self.assertEqual(self.client.get(reverse('autogestion_configurar',args=[self.jornada.pk])).status_code,405)

    def test_ranking_individual_reparto_exacto_empates_y_filtros(self):
        from .reporting import ranking_trabajadores
        filas=ranking_trabajadores(services.pesajes_para(self.admin))
        self.assertEqual(len(filas),2)
        self.assertEqual([f['kilos_estimados'] for f in filas],[Decimal('61.725'),Decimal('61.725')])
        self.assertEqual([f['puesto'] for f in filas],[1,1])
        self.assertEqual(sum(f['kilos_estimados'] for f in filas),self.pesaje.kilos)
        self.assertTrue(all(f['kilos_colleras']==Decimal('123.45') for f in filas))
        self.entrar(self.admin)
        r=self.client.get(reverse('reportes'))
        self.assertContains(r,'Ranking individual de trabajadores')
        self.assertContains(r,'Reparto estimado 50 / 50')
        self.assertEqual(len(r.context['ranking_trabajadores']),2)
        r=self.client.get(reverse('reportes'),{'desde':str(timezone.localdate()+timedelta(days=1))})
        self.assertEqual(r.context['ranking_trabajadores'],[])
        self.entrar(self.otro_jefe)
        r=self.client.get(reverse('reportes'))
        self.assertEqual(r.context['ranking_trabajadores'],[])
        self.assertNotContains(r,self.uno.username)

    def test_ranking_individual_conserva_integrantes_historicos(self):
        from .reporting import ranking_trabajadores
        self.collera.activa=False;self.collera.save(update_fields=['activa'])
        nueva=services.formar_collera(self.admin,{'nombre':'Nueva collera','cuadrilla':self.equipo,
                                      'trabajador_uno':self.uno,'trabajador_dos':self.ajeno})
        j=services.abrir_jornada(self.jefe,{'cuadrilla':self.equipo,'temporada':self.temporada,'cuartel':self.cuartel,
               'fecha':self.jornada.fecha+timedelta(days=1),'hora_inicio':time(8),'labor':'Cosecha','observaciones':''})
        services.guardar_pesaje(self.jefe,j,{'participacion':j.participaciones.get(),'kilos':Decimal('10.01'),
                                          'merma':Decimal('0'),'motivo_merma':'','calidad':'NACIONAL'})
        filas=ranking_trabajadores(services.pesajes_para(self.admin))
        self.assertEqual([f['id'] for f in filas],[self.uno.pk,self.dos.pk,self.ajeno.pk])
        self.assertEqual([f['kilos_estimados'] for f in filas],[Decimal('66.730'),Decimal('61.725'),Decimal('5.005')])
        self.assertEqual(filas[0]['colleras'],2)
        self.assertEqual(filas[1]['colleras'],1)
        self.assertEqual(sum(f['kilos_estimados'] for f in filas),Decimal('133.46'))

    def test_ranking_individual_numero_consultas_constante(self):
        from .reporting import ranking_trabajadores
        Pesaje.objects.bulk_create([Pesaje(participacion=self.participacion,responsable=self.jefe,
                       kilos='0.01',merma=0,calidad='NACIONAL') for _ in range(1000)])
        with self.assertNumQueries(2):
            filas=ranking_trabajadores(services.pesajes_para(self.admin))
        self.assertEqual(len(filas),2)
        self.assertEqual(sum(f['kilos_estimados'] for f in filas),Decimal('133.45'))

    def test_observaciones_jefe_edita_y_audita_sin_cambiar_otros_campos(self):
        self.entrar(self.jefe)
        ruta=reverse('jornada_observaciones',args=[self.jornada.pk])
        self.assertEqual(self.client.get(ruta).status_code,200)
        texto='Cosecha detenida por lluvia; retomamos a las 11:00.'
        r=self.client.post(ruta,{'observaciones':texto,'cerrada':'on','cuartel':'999'})
        self.assertEqual(r.status_code,302)
        self.jornada.refresh_from_db()
        self.assertEqual(self.jornada.observaciones,texto)
        self.assertFalse(self.jornada.cerrada)
        self.assertEqual(self.jornada.cuartel_id,self.cuartel.pk)
        self.assertTrue(AuditLog.objects.filter(accion='OBSERVACIONES_EDITADAS',usuario=self.jefe).exists())
        self.assertContains(self.client.get(reverse('cierre'),{'jornada':self.jornada.pk}),texto)
        self.client.post(ruta,{'observaciones':''})
        self.jornada.refresh_from_db();self.assertEqual(self.jornada.observaciones,'')

    def test_observaciones_cierre_temporada_permisos_y_limites(self):
        ruta=reverse('jornada_observaciones',args=[self.jornada.pk])
        for persona in [self.otro_jefe,self.admin,self.uno]:
            self.entrar(persona)
            self.assertEqual(self.client.post(ruta,{'observaciones':'Ajena'}).status_code,403)
        self.entrar(self.jefe)
        r=self.client.post(ruta,{'observaciones':'a'*501})
        self.assertIn('observaciones',r.context['form'].errors)
        services.cerrar_jornada(self.jefe,self.jornada)
        r=self.client.post(ruta,{'observaciones':'Intento posterior al cierre'})
        self.assertTrue(r.context['form'].non_field_errors())
        self.jornada.refresh_from_db();self.assertEqual(self.jornada.observaciones,'')
        services.reabrir_jornada(self.admin,self.jornada,'Corrección de observaciones')
        services.cerrar_temporada(self.admin,self.temporada)
        r=self.client.post(ruta,{'observaciones':'Intento en temporada cerrada'})
        self.assertTrue(r.context['form'].non_field_errors())
        self.jornada.refresh_from_db();self.assertEqual(self.jornada.observaciones,'')

    def test_observaciones_auditoria_completa_y_csrf(self):
        servicios=services
        texto='x'*500
        servicios.editar_observaciones(self.jefe,self.jornada,texto)
        partes=AuditLog.objects.filter(accion='OBSERVACIONES_DESPUES').order_by('pk')
        recuperado=''.join(p.detalle.split(': ',1)[1] for p in partes)
        self.assertEqual(recuperado,texto)
        cliente=Client(enforce_csrf_checks=True);cliente.force_login(self.jefe)
        r=cliente.post(reverse('jornada_observaciones',args=[self.jornada.pk]),{'observaciones':'sin token'})
        self.assertEqual(r.status_code,403)

    def test_reportes_paginar_sin_perder_filtros_totales_ni_ranking(self):
        Pesaje.objects.bulk_create([Pesaje(participacion=self.participacion,responsable=self.jefe,
                       kilos='1.00',merma=0,calidad='NACIONAL') for _ in range(60)])
        self.entrar(self.admin)
        parametros={'desde':str(timezone.localdate()),'hasta':str(timezone.localdate()),'page':'2'}
        r=self.client.get(reverse('reportes'),parametros)
        self.assertEqual(len(r.context['pesajes']),11)
        self.assertEqual(r.context['pagina'].paginator.count,61)
        self.assertEqual(r.context['totales']['kilos'],Decimal('183.45'))
        self.assertEqual(r.context['ranking_trabajadores'][0]['kilos_estimados'],Decimal('91.725'))
        self.assertIn('desde=',r.context['filtros_pagina'])
        r=self.client.get(reverse('reportes'),{'page':'2'})
        self.assertIn('page=1',r.content.decode())
        self.assertNotIn('desde=',r.context['filtros_pagina'])


class CargaDemoTest(TestCase):
    def test_carga_demo_repetible_conserva_existentes_y_permite_explorar(self):
        from io import StringIO
        from django.core.management import call_command
        admin=User.objects.create_user('admin',password='Una-clave-previa-123',rol='ADMIN')
        clave=admin.password
        real=Predio.objects.create(nombre='Mi predio existente',codigo='REAL-01',ubicacion='Talca')
        salida=StringIO()
        call_command('seed_operacion_demo',stdout=salida)
        self.assertEqual(Temporada.objects.count(),2)
        self.assertEqual(Collera.objects.count(),6)
        self.assertEqual(Cuadrilla.objects.count(),4)
        self.assertGreater(Pesaje.objects.count(),100)
        self.assertEqual(Jornada.objects.filter(fecha=timezone.localdate(),cerrada=False,autogestion_habilitada=True).count(),3)
        trabajador=User.objects.get(username='trabajador')
        marca=Asistencia.objects.get(trabajador=trabajador,jornada__fecha=timezone.localdate())
        self.assertIsNone(marca.entrada)
        self.assertIsNone(marca.salida)
        self.assertEqual(User.objects.filter(username__startswith='demo_disponible_').count(),2)
        self.assertFalse(Temporada.objects.get(nombre=f'DEMO · Temporada {timezone.localdate().year-1}').activa)
        modelos=[User,Predio,Huerto,Cultivo,Cuartel,Temporada,Cuadrilla,Collera,Jornada,Participacion,Asistencia,Pesaje,AuditLog]
        antes={m.__name__:m.objects.count() for m in modelos}
        call_command('seed_operacion_demo',stdout=StringIO())
        self.assertEqual(antes,{m.__name__:m.objects.count() for m in modelos})
        admin.refresh_from_db();real.refresh_from_db()
        self.assertEqual(admin.password,clave)
        self.assertTrue(admin.check_password('Una-clave-previa-123'))
        self.assertEqual(real.nombre,'Mi predio existente')
        self.client.force_login(admin)
        r=self.client.get(reverse('reportes'))
        self.assertGreater(r.context['totales']['kilos'],0)
        self.assertEqual(len(r.context['ranking']),6)
        temporadas=list(Temporada.objects.order_by('inicio'))
        r=self.client.get(reverse('comparativa_temporadas'),{'temporada_base':temporadas[0].pk,'temporada_comparada':temporadas[1].pk})
        self.assertEqual(r.status_code,200)
        self.assertTrue(r.context['hay_registros'])
