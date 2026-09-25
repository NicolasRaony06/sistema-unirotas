from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import MinValueValidator, RegexValidator
from authentication.models import User , UserRole
import re
# Create your models here.
class Municipio(models.Model):
    nome = models.CharField(max_length=100)
    codigo_ibge = models.CharField(max_length=7, unique=True)
    ofertado_pelo_sistema = models.BooleanField(default=False)
    municipios_relacionados = models.ManyToManyField('self', symmetrical=False, blank=True)
    gestor = models.ForeignKey(User,null=True,on_delete=models.SET_NULL)

    def __str__(self):
        return self.nome

    def save(self,*args,**kwargs):
        
        if self.gestor and self.gestor.role != UserRole.ADMIN:
            raise ValidationError("Este município só pode ter um gestor do tipo gerente.")

        super().save(*args,**kwargs)
        if self.gestor is not  None:
            self.municipios_relacionados.add(self)

class Bus(models.Model):
    license_plate_validator = RegexValidator(
        regex=r'^[A-Z]{3}-?[0-9][A-Z0-9][0-9]{2}$',
        message="A placa deve estar no padrão brasileiro antigo (AAA-1234) ou Mercosul (AAA1A23).",
        flags=re.IGNORECASE
    )

    license_plate = models.CharField(max_length=8, unique=True, validators=[license_plate_validator])
    name = models.CharField(max_length=50)
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    color = models.CharField(max_length=15, null=True, blank=True)
    identification_photo = models.ImageField(upload_to='bus/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    city = models.ForeignKey("Municipio", on_delete=models.CASCADE, related_name='buses')

    def __str__(self):
        return f"{self.name} {self.license_plate}" 