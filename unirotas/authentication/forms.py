from django import forms
from django.contrib.auth import get_user_model
from .models import StudentProfile
from django.core.exceptions import ValidationError
import re


User = get_user_model()

class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Senha'}
            ), label="Senha")
    
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirme a Senha'}
           ), label="Confirmação de Senha")

    class Meta:
        model = User
        fields = ["email", "full_name", "birth_date", "password"]
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'seu@email.com'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome Completo'}),
            'birth_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def is_password_invalid(self, password, confirm_password):
        if not password or not confirm_password:
            return True
        validation = re.search(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$", password)
        return not validation or password != confirm_password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        user.role = 'STUDENT'
        if commit:
            user.save()
        return user


    def clean(self):
        cleaned = super().clean()
        if not cleaned:
            return cleaned
        
        password = cleaned.get("password")
        confirm_password = cleaned.get("confirm_password")


        if self.is_password_invalid(password, confirm_password):
            raise ValidationError("senha invalida.")
        return cleaned


class StudentProfileForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = [# 'institution',
                  'course',
                  'period']
        widgets = {
            # 'institution': forms.Select(attrs={'class': 'form-select'}),
            'course': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Ciência da Computação'}),
            'period': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 12}),
        }