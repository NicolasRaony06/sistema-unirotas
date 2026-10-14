from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.core.validators import MinValueValidator, RegexValidator
from authentication.models import User , UserRole
import re
from django.db.models import Q, F

from multiselectfield import MultiSelectField

# Create your models here.
class Municipio(models.Model):
    nome = models.CharField(max_length=100)
    codigo_ibge = models.CharField(max_length=7, unique=True)
    ofertado_pelo_sistema = models.BooleanField(default=False)
    municipios_relacionados = models.ManyToManyField('self', symmetrical=False, blank=True)
    gestor = models.ForeignKey(User,null=True,on_delete=models.SET_NULL,related_name='municipio',blank=True,limit_choices_to={'role': 'MANAGER'})

    def __str__(self):
        return self.nome
    
    # def clean(self):
    #     if self.gestor and self.gestor.role != UserRole.MANAGER:
    #         raise ValidationError("Este município só pode ter um gestor do tipo gerente.")        
        
    def save(self,*args,**kwargs):
        super().save(*args,**kwargs)
        if self.gestor is not  None:
            self.municipios_relacionados.add(self)

class Bus(models.Model):
    license_plate_validator = RegexValidator(
        regex=r'^[A-Z]{3}-?[0-9][A-Z0-9][0-9]{2}$',
        message="A placa deve estar no padrão brasileiro antigo (AAA-1234) ou Mercosul (AAA1A23).",
        flags=re.IGNORECASE
    )

    license_plate = models.CharField(
        max_length=8, 
        unique=True, 
        validators=[license_plate_validator], 
        verbose_name="Placa", 
        error_messages={
            'unique': "Já existe um ônibus registrado com esta placa."
        }
    )
    name = models.CharField(max_length=50)
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1, message="A capacidade do ônibus deve ser maior ou igual a 1.")])
    color = models.CharField(max_length=15, null=True, blank=True)
    identification_photo = models.ImageField(upload_to='bus/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    city = models.ForeignKey("Municipio", on_delete=models.CASCADE, related_name='buses')

    class Meta:
        verbose_name = "Ônibus"
        verbose_name_plural = "Ônibus"
    
    def __str__(self):
        return f"{self.name} {self.license_plate}" 

class BusStop(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    city = models.ForeignKey("Municipio", on_delete=models.CASCADE, related_name='bus_stops')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Parada de ônibus"
        verbose_name_plural = "Paradas de ônibus"
        constraints = [
            models.UniqueConstraint(
                Lower('name'),
                'city',
                name="unique_bus_stop_per_city"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.city})"

class Institution(models.Model):
    name = models.CharField(max_length=150)
    city = models.ForeignKey("Municipio", on_delete=models.CASCADE, related_name='institutions')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Instituição"
        verbose_name_plural = "Instituições"
        constraints = [
            models.UniqueConstraint(
                Lower('name'),
                'city',
                name="unique_institution_per_city"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.city})"

class Linha(models.Model):
    nome = models.CharField(max_length=100)
    instituicoes_ofertadas = models.ManyToManyField(Institution)
    city = models.ForeignKey(Municipio,on_delete=models.PROTECT)
    motorista = models.ForeignKey(User,on_delete=models.PROTECT,limit_choices_to={'role': 'DRIVER'} )
    horario_inicio = models.TimeField()
    horario_fim = models.TimeField()
    dias_da_semana = [
        ('SEG', 'Segunda-feira'),
        ('TER', 'Terça-feira'),
        ('QUA', 'Quarta-feira'),
        ('QUI', 'Quinta-feira'),
        ('SEX', 'Sexta-feira'),
        ('SAB', 'Sábado'),
        ('DOM', 'Domingo'),
    ]
    dias_ofertados = MultiSelectField(
        choices= dias_da_semana,
        max_choices = 7,
        max_length= 30
    )

    def clean(self):
        if self.horario_inicio is not None and self.horario_fim is not None and self.horario_fim <= self.horario_inicio:
            raise ValidationError({"horario_fim": "O horário final deve ser posterior ao inicial."})        
        
    def save(self,*args,**kwargs):
        self.full_clean()
        super().save(*args,**kwargs)

    def __str__(self):
        return self.nome

class Rota(models.Model):
    nome = models.CharField(max_length=100)
    linha = models.ForeignKey(Linha, on_delete=models.CASCADE, related_name='linha_rota')

    class Direcao(models.TextChoices):
        IDA = 'IDA', 'Ida'
        VOLTA = 'VOLTA', 'Volta'

    direcao = models.CharField(max_length=5,choices=Direcao.choices)
    onibus = models.ForeignKey(Bus, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['linha','direcao'],
                name='unique_rota_linha_direcao'
            )
        ]

    def __str__(self):
        return f"{self.nome} ({self.get_direcao_display()})"


class TrechoViagem(models.Model):
    parada_inicio = models.ForeignKey(BusStop, on_delete=models.CASCADE, related_name='parada_origem')
    parada_fim = models.ForeignKey(BusStop, on_delete=models.CASCADE, related_name='parada_destino' )
    ordem = models.IntegerField()
    distancia_km = models.DecimalField(max_digits=6, decimal_places=2)
    rota = models.ForeignKey(Rota, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['rota','ordem'],
                name='unique_trecho_rota_ordem'
            ),
            models.CheckConstraint(
                condition=Q(ordem__gte=1),
                name= 'check_ordem_maior_0'
            ),
            models.CheckConstraint(
                condition=Q(distancia_km__gt=0),
                name='check_distancia_maior_0'
            ),
            models.CheckConstraint(
                condition=~Q(parada_inicio=F('parada_fim')),
                name='check_parada_inicio_diferente_parada_fim'
            )
        ]
        
    def __str__(self):
        return f"{self.parada_inicio} → {self.parada_fim} (ordem {self.ordem})"