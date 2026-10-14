# from django.contrib import admin
# from .models import *
# @admin.register(User)
# class UserAdmin(admin.ModelAdmin):
#     ...

# @admin.register(StudentProfile)
# class StudentAdmin(admin.ModelAdmin):
#     ...

# @admin.register(PersonelProfile)
# class PersonelAdmin(admin.ModelAdmin):
#     ...
# Register your models here.

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, StudentProfile, PersonelProfile


class UserAdminCreationForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput
    )

    password2 = forms.CharField(
        label="Confirme a senha",
        widget=forms.PasswordInput
    )

    class Meta:
        model = User
        fields = ("email", "full_name", "role")

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("As senhas não coincidem.")

        return password2

    def save(self, commit=True):
        user = super().save(commit=False)

        user.set_password(
            self.cleaned_data["password1"]
        )

        if commit:
            user.save()

        return user


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserAdminCreationForm

    list_display = ("email", "full_name", "role", "is_active")

    ordering = ("email",)

    fieldsets = (
        (None, {
            "fields": ("email", "password")
        }),
        ("Informações pessoais", {
            "fields": ("full_name", "role", "profile_picture")
        }),
        ("Permissões", {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            )
        }),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "email",
                "full_name",
                "role",
                "password1",
                "password2",
            ),
        }),
    )


@admin.register(StudentProfile)
class StudentAdmin(admin.ModelAdmin):
    pass


@admin.register(PersonelProfile)
class PersonelAdmin(admin.ModelAdmin):
    pass
