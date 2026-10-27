from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Rol(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        JEFE = "JEFE", "Jefe de Cuadrilla"
        TRABAJADOR = "TRABAJADOR", "Trabajador"

    rol = models.CharField(max_length=12, choices=Rol.choices, default=Rol.TRABAJADOR)

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.rol = self.Rol.ADMIN
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    """RNF04: acciones críticas auditadas con identidad, fecha, operación y detalle."""
    usuario = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    accion = models.CharField(max_length=40)
    detalle = models.CharField(max_length=200, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]


class Predio(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    codigo = models.CharField(max_length=24, unique=True)
    ubicacion = models.CharField(max_length=180)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Huerto(models.Model):
    predio = models.ForeignKey(Predio, on_delete=models.PROTECT, related_name='huertos')
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=24)

    class Meta:
        ordering = ['nombre']
        constraints = [
            models.UniqueConstraint(fields=['predio', 'nombre'], name='huerto_nombre_por_predio'),
            models.UniqueConstraint(fields=['predio', 'codigo'], name='huerto_codigo_por_predio'),
        ]

    def __str__(self):
        return f'{self.predio} / {self.nombre}'


class Cultivo(models.Model):
    nombre = models.CharField(max_length=80, unique=True)

    def __str__(self):
        return self.nombre


class Cuartel(models.Model):
    huerto = models.ForeignKey(Huerto, on_delete=models.PROTECT, related_name='cuarteles')
    cultivo = models.ForeignKey(Cultivo, on_delete=models.PROTECT)
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=24)
    superficie = models.DecimalField(max_digits=9, decimal_places=2)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        constraints = [
            models.UniqueConstraint(fields=['huerto', 'codigo'], name='cuartel_codigo_por_huerto'),
            models.UniqueConstraint(fields=['huerto', 'nombre'], name='cuartel_nombre_por_huerto'),
            models.CheckConstraint(condition=models.Q(superficie__gt=0), name='superficie_positiva'),
        ]

    def __str__(self):
        return f'{self.huerto} / {self.nombre}'


class Temporada(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    inicio = models.DateField()
    fin = models.DateField()
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ['-inicio']
        constraints = [models.CheckConstraint(condition=models.Q(fin__gte=models.F('inicio')), name='temporada_fechas_coherentes')]

    def __str__(self):
        return self.nombre

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.inicio and self.fin and self.fin < self.inicio:
            raise ValidationError({'fin': 'El término debe ser posterior o igual al inicio.'})


class Cuadrilla(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    jefe = models.ForeignKey(User, on_delete=models.PROTECT, related_name='cuadrillas', limit_choices_to={'rol': 'JEFE', 'is_active': True})

    def __str__(self):
        return self.nombre


class Collera(models.Model):
    nombre = models.CharField(max_length=80, unique=True)
    cuadrilla = models.ForeignKey(Cuadrilla, on_delete=models.PROTECT, related_name='colleras')
    trabajador_uno = models.ForeignKey(User, on_delete=models.PROTECT, related_name='colleras_uno')
    trabajador_dos = models.ForeignKey(User, on_delete=models.PROTECT, related_name='colleras_dos')
    activa = models.BooleanField(default=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=~models.Q(trabajador_uno=models.F('trabajador_dos')), name='collera_dos_distintos')]

    def __str__(self):
        return self.nombre

    @property
    def integrantes(self):
        return (self.trabajador_uno, self.trabajador_dos)


class Jornada(models.Model):
    cuadrilla = models.ForeignKey(Cuadrilla, on_delete=models.PROTECT, related_name='jornadas')
    jefe = models.ForeignKey(User, on_delete=models.PROTECT, related_name='jornadas_responsable')
    temporada = models.ForeignKey(Temporada, on_delete=models.PROTECT, related_name='jornadas')
    cuartel = models.ForeignKey(Cuartel, on_delete=models.PROTECT, related_name='jornadas')
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    labor = models.CharField(max_length=100, default='Cosecha')
    observaciones = models.CharField(max_length=500, blank=True)
    autogestion_habilitada = models.BooleanField(default=False, verbose_name='Habilitar autogestión de asistencia')
    cerrada = models.BooleanField(default=False)
    cerrada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-fecha', 'cuadrilla__nombre']
        constraints = [models.UniqueConstraint(fields=['cuadrilla', 'fecha'], name='una_jornada_cuadrilla_fecha')]

    def __str__(self):
        return f'{self.cuadrilla} · {self.fecha:%d/%m/%Y}'

    @property
    def editable(self):
        return not self.cerrada and self.temporada.activa


class Participacion(models.Model):
    """Conserva la cuadrilla y miembros históricos aunque la collera sea trasladada."""
    jornada = models.ForeignKey(Jornada, on_delete=models.PROTECT, related_name='participaciones')
    collera = models.ForeignKey(Collera, on_delete=models.PROTECT, related_name='participaciones')
    fecha = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['collera', 'fecha'], name='collera_una_cuadrilla_por_dia')]

    def __str__(self):
        return self.collera.nombre


class Asistencia(models.Model):
    jornada = models.ForeignKey(Jornada, on_delete=models.PROTECT, related_name='asistencias')
    trabajador = models.ForeignKey(User, on_delete=models.PROTECT, related_name='asistencias')
    entrada = models.TimeField(null=True, blank=True)
    salida = models.TimeField(null=True, blank=True)
    ausente = models.BooleanField(default=False)
    validada = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['jornada', 'trabajador'], name='asistencia_unica'),
            models.CheckConstraint(condition=models.Q(salida__isnull=True) | (models.Q(entrada__isnull=False) & models.Q(salida__gt=models.F('entrada'))), name='salida_posterior_entrada'),
            models.CheckConstraint(condition=models.Q(ausente=False) | (models.Q(entrada__isnull=True) & models.Q(salida__isnull=True)), name='ausente_sin_horas'),
        ]

    @property
    def horas(self):
        from datetime import datetime
        from decimal import Decimal
        if self.entrada and self.salida:
            delta = datetime.combine(self.jornada.fecha, self.salida) - datetime.combine(self.jornada.fecha, self.entrada)
            return Decimal(str(delta.total_seconds())) / Decimal('3600')
        return Decimal('0')

    @property
    def atraso(self):
        return bool(self.entrada and self.entrada > self.jornada.hora_inicio)


class Pesaje(models.Model):
    class Calidad(models.TextChoices):
        EXPORTACION = 'EXPORTACION', 'Exportación'
        NACIONAL = 'NACIONAL', 'Mercado nacional'
        INDUSTRIAL = 'INDUSTRIAL', 'Industrial'

    participacion = models.ForeignKey(Participacion, on_delete=models.PROTECT, related_name='pesajes')
    kilos = models.DecimalField(max_digits=10, decimal_places=2)
    merma = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    motivo_merma = models.CharField(max_length=200, blank=True)
    calidad = models.CharField(max_length=16, choices=Calidad.choices)
    responsable = models.ForeignKey(User, on_delete=models.PROTECT)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado']
        constraints = [
            models.CheckConstraint(condition=models.Q(kilos__gt=0), name='kilos_positivos'),
            models.CheckConstraint(condition=models.Q(merma__gte=0), name='merma_no_negativa'),
            models.CheckConstraint(condition=models.Q(merma=0) | ~models.Q(motivo_merma=''), name='merma_con_motivo'),
        ]
