from django import forms
from django.contrib.auth import get_user_model, password_validation
from .models import StudentProfile
from django.core.exceptions import ValidationError
import re
from datetime import date

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
        fields = [
            "full_name",
            "birth_date"]
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome Completo'}),
            'birth_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
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
            self.add_error(
                'password', 'A senha tem que atender a todos os requisitos e coincidir com o confirmar senha.'
            )

        if password:
            try:
                user = User(email=cleaned.get("email"), full_name=cleaned.get("full_name"))
                password_validation.validate_password(password, user=user)
            except ValidationError as e:
                self.add_error('password', e.messages)

        data = cleaned.get("birth_date")
        if data and data > date.today():
            self.add_error("birth_date", "A data de nascimento não pode estar no futuro.")

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
        fields = [
                  'course',
                  'period']
        widgets = {
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
            'placeholder': 'Senha atual'
        }), 
        label="Senha atual"
    )
    
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nova senha'
        }),
        label="Nova senha"
    )

    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirme a nova senha'
        }),
        label="Confirmação de Senha"
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("new_password1")
        confirm_password = cleaned.get("new_password2")

        if password and confirm_password and password != confirm_password:
            self.add_error('new_password2', 'A senha tem que ser igual a confirmação de senha')
        elif self.is_password_invalid(password, confirm_password):
            self.add_error("new_password1", "A senha tem que atender a todos os requisitos")

        if password:
            try:
                password_validation.validate_password(password, user=self.user)
            except ValidationError as e:
                self.add_error('new_password1', e.messages)
        return cleaned
