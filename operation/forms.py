from django import forms
from .models import UsuarioDaViagem

class alunoForm(forms.ModelForm):
    class Meta:
        model = UsuarioDaViagem
        fields = ['direcao', 'horario_saida_aluno']
        labels = {'direcao':'', 'horario_saida_aluno':''}