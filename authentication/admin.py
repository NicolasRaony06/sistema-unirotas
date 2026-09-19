from django.contrib import admin
from .models import *
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    ...

@admin.register(StudentProfile)
class StudentAdmin(admin.ModelAdmin):
    ...
# Register your models here.
