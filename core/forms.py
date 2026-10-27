from django.contrib.auth.forms import UserCreationForm

from .models import User


class UsuarioForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "rol")


from decimal import Decimal
from django import forms
from django.db.models import Q
from django.utils import timezone
from .models import (Asistencia, Collera, Cuadrilla, Cuartel, Cultivo, Huerto,
                     Jornada, Participacion, Pesaje, Predio, Temporada)


class PredioForm(forms.ModelForm):
    class Meta:
        model = Predio
        fields = ['nombre', 'codigo', 'ubicacion']


class HuertoForm(forms.ModelForm):
    class Meta:
        model = Huerto
        fields = ['predio', 'nombre', 'codigo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['predio'].queryset = Predio.objects.filter(Q(activo=True) | Q(pk=self.instance.predio_id))


class CultivoForm(forms.ModelForm):
    class Meta:
        model = Cultivo
        fields = ['nombre']


class CuartelForm(forms.ModelForm):
    superficie = forms.DecimalField(max_digits=9, decimal_places=2, min_value=Decimal('0.01'))

    class Meta:
        model = Cuartel
        fields = ['huerto', 'cultivo', 'nombre', 'codigo', 'superficie']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['huerto'].queryset = Huerto.objects.filter(Q(predio__activo=True) | Q(pk=self.instance.huerto_id)).select_related('predio')


class TemporadaForm(forms.ModelForm):
    class Meta:
        model = Temporada
        fields = ['nombre', 'inicio', 'fin']
        widgets = {key: forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d') for key in ['inicio', 'fin']}


class CuadrillaForm(forms.ModelForm):
    class Meta:
        model = Cuadrilla
        fields = ['nombre', 'jefe']


class ColleraForm(forms.ModelForm):
    class Meta:
        model = Collera
        fields = ['nombre', 'cuadrilla', 'trabajador_uno', 'trabajador_dos']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ocupados = list(Collera.objects.filter(activa=True).values_list('trabajador_uno_id', flat=True))
        ocupados += list(Collera.objects.filter(activa=True).values_list('trabajador_dos_id', flat=True))
        for key in ['trabajador_uno', 'trabajador_dos']:
            self.fields[key].queryset = User.objects.filter(rol=User.Rol.TRABAJADOR, is_active=True).exclude(pk__in=ocupados)


class JornadaForm(forms.ModelForm):
    class Meta:
        model = Jornada
        fields = ['cuadrilla', 'temporada', 'cuartel', 'fecha', 'hora_inicio', 'labor', 'observaciones', 'autogestion_habilitada']
        widgets = {'fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'hora_inicio': forms.TimeInput(attrs={'type': 'time'}),
                   'observaciones': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cuadrilla'].queryset = Cuadrilla.objects.filter(jefe=actor)
        self.fields['temporada'].queryset = Temporada.objects.filter(activa=True)
        self.fields['cuartel'].queryset = Cuartel.objects.filter(activo=True, huerto__predio__activo=True).select_related('huerto__predio')
        self.fields['fecha'].initial = timezone.localdate()
        self.fields['hora_inicio'].initial = '08:00'


class PesajeForm(forms.ModelForm):
    kilos = forms.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'), widget=forms.NumberInput(attrs={'step': '0.01', 'inputmode': 'decimal'}))
    merma = forms.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0'), initial=0, widget=forms.NumberInput(attrs={'step': '0.01', 'inputmode': 'decimal'}))

    class Meta:
        model = Pesaje
        fields = ['participacion', 'kilos', 'calidad', 'merma', 'motivo_merma']
        labels = {'participacion': 'Collera', 'motivo_merma': 'Motivo de merma'}

    def __init__(self, *args, jornada, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['participacion'].queryset = Participacion.objects.filter(jornada=jornada).select_related('collera')

    def clean(self):
        values = super().clean()
        if values.get('merma', 0) and not values.get('motivo_merma', '').strip():
            self.add_error('motivo_merma', 'Indica el motivo de la merma.')
        return values


class MarcaForm(forms.Form):
    accion = forms.ChoiceField(choices=[('entrada', 'Entrada'), ('salida', 'Salida'), ('ausente', 'Ausente')])
    hora = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type': 'time'}))

    def clean(self):
        data = super().clean()
        if data.get('accion') in ('entrada', 'salida') and not data.get('hora'):
            self.add_error('hora', 'Indica la hora de la marca.')
        return data


class MotivoForm(forms.Form):
    motivo = forms.CharField(min_length=8, max_length=180, widget=forms.Textarea(attrs={'rows': 3}))


class ReporteForm(forms.Form):
    desde = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    predio = forms.ModelChoiceField(queryset=Predio.objects.all(), required=False, empty_label='Todos los predios')
    cuartel = forms.ModelChoiceField(queryset=Cuartel.objects.select_related('huerto__predio'), required=False, empty_label='Todos los cuarteles')

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        if actor.rol == User.Rol.JEFE:
            self.fields['predio'].queryset = Predio.objects.filter(huertos__cuarteles__jornadas__jefe=actor).distinct()
            self.fields['cuartel'].queryset = Cuartel.objects.filter(jornadas__jefe=actor).select_related('huerto__predio').distinct()

    def clean(self):
        data = super().clean()
        if data.get('desde') and data.get('hasta') and data['hasta'] < data['desde']:
            self.add_error('hasta', 'La fecha final debe ser igual o posterior a la inicial.')
        if data.get('predio') and data.get('cuartel') and data['cuartel'].huerto.predio_id != data['predio'].pk:
            self.add_error('cuartel', 'El cuartel no pertenece al predio seleccionado.')
        return data


class UsuarioEditarForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'rol', 'is_active']
        labels = {'is_active': 'Cuenta activa'}


class ColleraEditarForm(forms.ModelForm):
    class Meta:
        model = Collera
        fields = ['nombre']


class TrasladoForm(forms.Form):
    destino = forms.ModelChoiceField(queryset=Cuadrilla.objects.none(), label='Cuadrilla de destino')
    motivo = forms.CharField(min_length=8, max_length=160, widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, collera, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['destino'].queryset = Cuadrilla.objects.filter(jefe__is_active=True, jefe__rol=User.Rol.JEFE).exclude(pk=collera.cuadrilla_id)


class AutogestionForm(forms.Form):
    habilitada = forms.BooleanField(required=False, label='Permitir que los trabajadores marquen su propia asistencia')


class ComparativaForm(forms.Form):
    temporada_base = forms.ModelChoiceField(queryset=Temporada.objects.all(), label='Temporada de referencia')
    temporada_comparada = forms.ModelChoiceField(queryset=Temporada.objects.all(), label='Temporada a comparar')
    predio = forms.ModelChoiceField(queryset=Predio.objects.all(), required=False, empty_label='Todos los predios')
    cultivo = forms.ModelChoiceField(queryset=Cultivo.objects.all(), required=False, empty_label='Todos los cultivos')

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        if actor.rol == User.Rol.JEFE:
            for key in ['temporada_base', 'temporada_comparada']:
                self.fields[key].queryset = Temporada.objects.filter(jornadas__jefe=actor).distinct()
            self.fields['predio'].queryset = Predio.objects.filter(huertos__cuarteles__jornadas__jefe=actor).distinct()
            self.fields['cultivo'].queryset = Cultivo.objects.filter(cuartel__jornadas__jefe=actor).distinct()

    def clean(self):
        data = super().clean()
        if data.get('temporada_base') and data.get('temporada_base') == data.get('temporada_comparada'):
            self.add_error('temporada_comparada', 'Selecciona dos temporadas diferentes.')
        return data


class ObservacionesForm(forms.Form):
    observaciones = forms.CharField(required=False, max_length=500, label='Observaciones de la jornada',
                                   widget=forms.Textarea(attrs={'rows': 5}))
