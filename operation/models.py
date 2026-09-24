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
        return f'{self.linha} ({self.data})'

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
    estudante = models.ForeignKey('authentication.StudentProfile', on_delete=models.CASCADE, related_name='viagens')
    viagem = models.ForeignKey(Viagem, on_delete=models.CASCADE, related_name='usuarios')
    direcao = models.CharField(max_length=20, choices=[
        ('ida', 'Ida'),
        ('volta', 'Volta'),
        ('ida e volta', 'Ida e Volta'),
    ])
    horario_saida_aluno = models.TimeField()
    presente = models.BooleanField(default=False)
    instituicao = models.CharField(max_length=100)
    moderador = models.BooleanField(default=False)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['estudante', 'viagem'], name='unique_estudante_viagem')
        ]
    
    def __str__(self):
        return f'{self.estudante} - {self.viagem} ({self.direcao})'