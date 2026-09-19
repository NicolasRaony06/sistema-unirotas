from django.core.exceptions import ValidationError
from django.db import models
from authentication.models import User
# Create your models here.
class Municipio(models.Model):
    nome = models.CharField(max_length=100)
    codigo_ibge = models.CharField(max_length=7, unique=True)
    ofertado_pelo_sistema = models.BooleanField(default=False)
    municipios_relacionados = models.ManyToManyField('self', symmetrical=False, blank=True)
    gestor = models.ForeignKey(User,null=True,on_delete=models.SET_NULL)

    def __str__(self):
        return self.nome

    @classmethod
    def cadastrar_municipio(cls,codigo_ibge,**dados_restantes):
        municipio, criado = Municipio.objects.get_or_create(codigo_ibge=codigo_ibge,defaults= dados_restantes)

        return municipio, criado

    def save(self,*args,**kwargs):
        super().save(*args,**kwargs)
        if self.gestor is not  None:
            self.municipios_relacionados.add(self)
        