from django import forms
from .models import Bus, Municipio, BusStop, Institution, Linha, Rota, TrechoViagem

from authentication.models import UserRole, User
from django.shortcuts import get_object_or_404
from django.db.models import Q

class BusForm(forms.ModelForm):
    class Meta:
        model = Bus
        fields = ['license_plate', 'name', 'capacity', 'color', 'identification_photo']
        widgets = {
            'license_plate': forms.TextInput(attrs={'placeholder': 'Ex: ABC-1234'}),
            'name': forms.TextInput(attrs={'placeholder': 'Ex: Ônibus 001'}),
            'capacity': forms.NumberInput(attrs={'placeholder': 'Ex: 50'}),
            'color': forms.TextInput(attrs={'placeholder': 'Ex: Amarelo'}),
            'identification_photo': forms.FileInput()
        }

    def clean_license_plate(self):
        data = self.cleaned_data['license_plate']
        data = data.upper().replace('-', '').strip()
        
        return data

class MunicipioForm(forms.ModelForm):
    class Meta:
        model = Municipio
        fields = ['nome', 'codigo_ibge','gestor']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        managers = self.fields['gestor'].queryset

        self.fields['gestor'].queryset = managers.filter(municipio=None)

class BusStopForm(forms.ModelForm):
    class Meta:
        model = BusStop
        fields = ['name', 'description', 'city']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Ex: Atacarejo'}),
            'description': forms.Textarea(attrs={
                "placeholder": "Descreva a parada",
                "rows": 4,
            }),
            'city': forms.Select()
        }

    def __init__(self, *args, **kwargs):
        city = kwargs.pop('city', None)
        super().__init__(*args, **kwargs)

        if city:
            related_cities = city.municipios_relacionados.values_list('id', flat=True)

            self.fields['city'].queryset = Municipio.objects.filter(
                Q(id=city.id) | (Q(id__in=related_cities) & Q(ofertado_pelo_sistema=False))).distinct()
        
class InstitutionForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = ['name', 'city']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Ex: IFRN'}),
            'city': forms.Select()
        }

    def __init__(self, *args, **kwargs):
        city = kwargs.pop('city', None)
        super().__init__(*args, **kwargs)

        if city:
            related_cities = city.municipios_relacionados.values_list('id', flat=True)
            
            self.fields['city'].queryset = Municipio.objects.filter(
                Q(id=city.id) | (Q(id__in=related_cities) & Q(ofertado_pelo_sistema=False))).distinct()

class LinhaForm(forms.ModelForm):
    class  Meta:
        model = Linha
        fields = ['nome','motorista','horario_inicio','horario_fim','dias_ofertados','instituicoes_ofertadas']
        

class RotaForm(forms.ModelForm):
    class Meta:
        model = Rota
        fields = ['nome','direcao','onibus']

class TrechoViagemForm(forms.ModelForm):
    class Meta:
        model = TrechoViagem
        fields = ['parada_inicio','parada_fim','ordem','distancia_km']

class BaseInviteForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={
            'placeholder': 'email@example.com'
    }))
    confirm_email = forms.EmailField(widget=forms.EmailInput(attrs={
        'placeholder': 'email@example.com'
    }))

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        confirm_email = cleaned_data.get('confirm_email')

        if email and confirm_email:
            if email != confirm_email:
                self.add_error(
                    'confirm_email', 'A confirmação de email não corresponde ao email digitado.'
                )
        return cleaned_data

class InviteDriverForm(BaseInviteForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.field['email'].widget.attrs['placeholder'] = 'motorista@example.com'
        self.field['confirm_email'].widget.attrs['placeholder'] = 'motorista@example.com'
    
class InviteStudentForm(BaseInviteForm):
    institution = forms.ChoiceField(choices=(), widget=forms.Select())

    def __init__(self, *args, **kwargs):
        institutions_id = kwargs.pop('institutions_id', None)
        super().__init__(*args, **kwargs)
        self.field['email'].widget.attrs['placeholder'] = 'estudante@example.com'
        self.field['confirm_email'].widget.attrs['placeholder'] = 'estudante@example.com'

        if institutions_id:
            institutions = Institution.objects.filter(
                id__in=institutions_id, 
                is_active=True
            ).values_list('id', 'name', 'city__nome')

            self.fields['institution'].choices = [(id, f"{name} ({city})") for id, name, city in institutions] 

class AssociateCityManager(forms.Form):
    manager = forms.ChoiceField(choices=(), widget=forms.Select())
    city = forms.ChoiceField(choices=(), widget=forms.Select())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        managers = User.objects.filter(municipio=None, role=UserRole.MANAGER).values_list('id', 'email')
        cities = Municipio.objects.filter(ofertado_pelo_sistema=False, gestor=None).values_list('id', 'nome')

        self.fields['manager'].choices = [('', 'Selecionar Gestor')] + list(managers)
        self.fields['city'].choices = [('', 'Selecionar Município')] + list(cities)

