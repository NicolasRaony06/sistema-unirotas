from django import forms
from .models import Bus, Municipio, BusStop, Institution, Linha, Rota, TrechoViagem
from django.shortcuts import get_object_or_404
from django.db.models import Q

class BusForm(forms.ModelForm):
    class Meta:
        model = Bus
        fields = ['license_plate', 'name', 'capacity', 'color', 'identification_photo']
        widgets = {
            'license_plate': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Ex: ABC-1234'}),
            'name': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Ex: Ônibus 001'}),
            'capacity': forms.NumberInput(attrs={'class': 'input-field', 'placeholder': 'Ex: 50'}),
            'color': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Ex: Amarelo'}),
            #'identification_photo': forms.FileInput(attrs={'class': '', 'label': 'Envie uma foto de identificação do ônibus'})
        }

    def clean_license_plate(self):
        data = self.cleaned_data['license_plate']
        data = data.upper().replace('-', '').strip()
        
        return data

class MunicipioForm(forms.ModelForm):
    class Meta:
        model = Municipio
        fields = ['nome', 'codigo_ibge','gestor']

class BusStopForm(forms.ModelForm):
    class Meta:
        model = BusStop
        fields = ['name', 'description', 'city']

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