from django import forms
from .models import Bus

class BusForm(forms.ModelForm):
    class Meta:
        model = Bus
        fields = ['license_plate', 'name', 'capacity', 'color', 'identification_photo']
        widgets = {
            'license_plate': forms.TextInput(attrs={'class': '', 'placeholder': 'Digite a placa do ônibus'}),
            'name': forms.TextInput(attrs={'class': '', 'placeholder': 'Digite o nome identificador do ônibus'}),
            'capacity': forms.NumberInput(attrs={'class': '', 'placeholder': 'Digite a capacidade do ônibus'}),
            'color': forms.TextInput(attrs={'class': '', 'placeholder': 'Digite cor predominante do ônibus'}),
            'identification_photo': forms.FileInput(attrs={'class': '', 'label': 'Envie uma foto de identificação do ônibus'})
        }