from django import forms
from django.contrib.auth import get_user_model, password_validation
from .models import StudentProfile
from django.core.exceptions import ValidationError
import re


User = get_user_model()

class Validation:
    def is_password_invalid(self, password, confirm_password):
            if not password or not confirm_password:
                return True
            validation = re.search(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$", password)
            return not validation or password != confirm_password
    

class UserRegistrationForm(forms.ModelForm, Validation):
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
        fields = ["email", "full_name", "birth_date"]
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'seu@email.com'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome Completo'}),
            'birth_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
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

        email = cleaned.get("email")
        if email:
            cleaned["email"] = email.lower().strip()

        return cleaned


class AvatarForm(forms.Form):
    profile_picture = forms.ImageField(widget=forms.ClearableFileInput(attrs={
            'id': 'file-input',
            'style': 'display: none;',
            'onchange': 'this.form.submit()'
        }))

    def clean_profile_picture(self):
        imagem = self.cleaned_data.get("profile_picture")
        if imagem:
            if imagem.size > 2 * 1024 * 1024:
                raise ValidationError("A imagem é muito grande. O limite é de 2MB.")
        return imagem

class StudentProfileForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = [# 'city',
                  # 'institution',
                  'course',
                  'period']
        widgets = {
            # 'institution': forms.Select(attrs={'class': 'form-select'}),
            # 'city': forms.Select(attrs={'class': 'form-select'}),
            'course': forms.TextInput(attrs={'class': 'form-control',
                                             'placeholder': 'Ex: Ciência da Computação'}
                                             ),
            'period': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 12, 'placeholder': "periodo cursado"}),
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned:
            return cleaned
        period = cleaned.get("period")
        if not period:
            raise forms.ValidationError("O periodo deve ser de 1 a 12")

        if cleaned.get("period") > 12 or cleaned.get("period") < 1:
            raise forms.ValidationError("O periodo deve ser de 1 a 12")

        return cleaned

class LoginForm(forms.Form):
    email = forms.EmailField(
            widget=forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'seu@email.com'}
                ), label = "email")

    password = forms.CharField(
            widget=forms.PasswordInput(attrs={
                'class': 'form-control',
                'placeholder': 'Senha'}
                ), label="Senha")

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        if email:
            cleaned["email"] = email.lower().strip()
        return cleaned

class ChangePassword(forms.Form, Validation):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Senha'}
            ), label="Senha")
    
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirme a Senha'}
           ), label="Confirmação de Senha")

    new_password2 = forms.CharField(
            widget=forms.PasswordInput(attrs={
                'class': 'form-control',
                'placeholder': 'Confirme a Senha'}
               ), label="Confirmação de Senha")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)

    def is_password_invalid(self, password, confirm_password):
        is_invalid = super().is_password_invalid(password, confirm_password)
        if not is_invalid:
            password_validation.validate_password(password, user=self.user)
            return False
        return True

    def clean(self):
        cleaned = super().clean()
        if not cleaned:
            return cleaned
        
        password = cleaned.get("new_password1")
        confirm_password = cleaned.get("new_password2")

        if self.is_password_invalid(password, confirm_password):
            raise ValidationError("senha invalida.")

        return cleaned
