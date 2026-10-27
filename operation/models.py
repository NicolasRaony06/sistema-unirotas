from django.db import models
from django.utils import timezone
from management.models import *
from management.models import BusStop
# class Linha(models.Model):
#     nome = models.CharField(max_length=50)
#     origem = models.CharField(max_length=50)
#     destino = models.CharField(max_length=50)
#     dias_funcionamento = models.CharField(max_length=50, default='Seg - Sex')
#     horario_inicio = models.TimeField()
#     horario_fim = models.TimeField()

#     def __str__(self):
#         return self.nome
    
class Viagem(models.Model):
    rota = models.ForeignKey(Rota, on_delete=models.CASCADE)
    data = models.DateTimeField()
    status = models.CharField(max_length=20, choices=[
        ('aguardando', 'Aguardando'),
        ('em_andamento', 'Em andamento'),
        ('concluida', 'Concluida'),
    ])
    momento_iniciado = models.DateTimeField(null=True, blank=True)
    momento_finalizado = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.rota.linha} - {self.rota.direcao} ({self.data})'

    def comecar(self):
        self.status = 'em_andamento'
        self.momento_iniciado = timezone.now()
        self.save()

    def concluir(self, motorista):
        self.status = 'concluida'
        self.momento_finalizado = timezone.now()
        self.save()

        proxima = Viagem.objects.filter(
            rota=self.rota,
            status='aguardando',
            data__gte=self.data,
            rota__linha__motorista = motorista
        ).exclude(pk=self.pk).order_by('data').first()

        if proxima:
            proxima.status = 'aguardando'
            proxima.save()
            return proxima
        return None
    
    def criar_paradas(self):
        trechos = TrechoViagem.objects.filter(rota=self.rota).order_by('ordem')
        primeiro = trechos.first()

        if primeiro is None:
            return

        ViagemParada.objects.create(viagem=self, parada=primeiro.parada_inicio)

        for trecho in trechos:
            ViagemParada.objects.create(viagem=self, parada=trecho.parada_fim)
    
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
            models.UniqueConstraint(
                fields=['estudante', 'viagem'],
                name='unique_estudante_viagem',
                violation_error_message='Esse aluno já está registrado nessa viagem.'
            ),
            models.UniqueConstraint(
                fields=['viagem'],
                condition=models.Q(moderador=True),
                name='unique_moderador_por_viagem',
                violation_error_message='Essa viagem já possui um moderador definido.'
            ),
    ]
    
    def __str__(self):
        return f'{self.estudante} - {self.viagem} ({self.direcao})'
    
class ViagemParada(models.Model):
    viagem = models.ForeignKey(Viagem, on_delete=models.CASCADE, related_name='paradas')
    parada = models.ForeignKey(BusStop, on_delete=models.PROTECT)
    momento_de_conclusao = models.DateTimeField(blank=True, null=True, )
    status = models.CharField(max_length=30, choices =[
        ('Aguardando', 'Aguardando'),
        ('Concluido', 'Concluido'),
    ], default='Aguardando')
    data_criacao = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'{self.viagem} - {self.parada}'
    
    