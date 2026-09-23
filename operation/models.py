from django.db import models
from django.utils import timezone

class Viagem(models.Model):
    linha = models.CharField(max_length=50)
    data = models.DateTimeField()
    status = models.CharField(max_length=20, choices=[
        ('aguardando', 'Aguardando'),
        ('em_anamento', 'Em andamento'),
        ('concluida', 'Concluida'),
    ])
    momento_iniciado = models.DateTimeField(null=True, blank=True)
    momento_finalizado = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.linha

    def comecar(self):
        self.status = 'em_andamento'
        self.momento_iniciado = timezone.now()
        self.save()

    def concluir(self):
        self.status = 'concluida'
        self.momento_finalizado = timezone.now()
        self.save()

        proxima = Viagem.objects.filter(
            linha=self.linha,
            status='aguardando',
            data__gte=self.data
        ).exclude(pk=self.pk).order_by('data').first()

        if proxima:
            proxima.status = 'aguardando'
            proxima.save()
            return proxima
        return None
    
class UsuarioDaViagem(models.Model):
    estudante = models.CharField(max_length=50)
    Viagem