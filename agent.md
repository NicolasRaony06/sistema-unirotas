# AGENT.md — Contexto & Diretrizes do Projeto

Este documento define as convenções de arquitetura, decisões de modelagem, regras de negócio e padrões de código para a construção do **Sistema de Gestão de Transporte Escolar Municipal (MVP)** em Django.

---

## 1. Filosofia de Design & Arquitetura

### Normalização do Banco de Dados

O banco de dados preserva estritamente a integridade referencial (**3ª Forma Normal**).

Evita-se a desnormalização desnecessária de campos, como replicar `line` e `route` em tabelas filhas que já possuem `ForeignKey` para um cabeçalho.

### Camada de Serviço (Service Layer)

Toda a regra de negócio, orquestração de transações, criação de instâncias relacionadas e cálculos agregados devem residir na camada de **Services (`services.py`)**.

Views, Serializers e Models devem permanecer magros.

### Transações Atômicas

Operações que envolvem múltiplos `INSERT`s/`UPDATE`s relacionais, como gravação de sessão + métrica, devem ser encapsuladas em:

```python
@transaction.atomic
```

### Cálculos Dinâmicos

Métricas como velocidade:

$$
v = \frac{d}{t}
$$

e projeção de horário estimado de chegada (**ETA**) são derivadas dinamicamente no Service, cruzando dados estáticos de rotas com dados históricos de execução.

---

# 2. Modelos de Dados Core (`models.py`)

## 2.1. Sequenciamento de Rota (`RotaParadas`)

Representa os trechos/arestas ordenados que compõem uma rota, seja **Ida** ou **Volta**.

```python
from django.db import models


class RotaParadas(models.Model):
    rota = models.ForeignKey(
        'Rota',
        on_delete=models.CASCADE,
        related_name='paradas_trechos'
    )
    parada_inicio = models.ForeignKey(
        'Parada',
        on_delete=models.CASCADE,
        related_name='trechos_origem'
    )
    parada_fim = models.ForeignKey(
        'Parada',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='trechos_destino'
    )
    distancia = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    ordem = models.PositiveIntegerField()

    class Meta:
        ordering = ['ordem']
        unique_together = ('rota', 'ordem')

    def __str__(self):
        return (
            f"{self.rota} - Pos {self.ordem}: "
            f"{self.parada_inicio} -> {self.parada_fim or 'Fim'}"
        )
```

---

## 2.2. Execução Diária & Métricas de Tempo (`Master-Detail`)

Estrutura de cabeçalho e detalhe para registrar o histórico de viagens e o desempenho dos veículos em cada trecho.

### `LastRouteDay`

```python
class LastRouteDay(models.Model):
    line = models.CharField(
        max_length=50
    )  # Substituir por FK quando o model Linha for integrado

    route = models.CharField(
        max_length=50
    )  # Substituir por FK quando o model Rota for integrado

    date = models.DateField(
        auto_now_add=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ['-created_at']
```

### `StopMetrics`

```python
class StopMetrics(models.Model):
    last_route_day = models.ForeignKey(
        LastRouteDay,
        on_delete=models.CASCADE,
        related_name='stop_metrics'
    )

    start_stop = models.CharField(
        max_length=100
    )

    end_stop = models.CharField(
        max_length=100
    )

    start_time = models.TimeField()
    end_time = models.TimeField()

    @property
    def line(self):
        return self.last_route_day.line

    @property
    def route(self):
        return self.last_route_day.route
```

---

## 2.3. Presença / Demanda de Alunos (`StudentsUsingBus`)

Mapeia a intenção de uso do transporte pelos estudantes para cálculo de ocupação por rota e dia.

```python
from django.contrib.auth.models import User


class StudentsUsingBus(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bus_usages'
    )

    route = models.ForeignKey(
        'Rota',
        on_delete=models.CASCADE,
        related_name='student_presences'
    )

    day = models.DateField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        unique_together = ('user', 'route', 'day')
```

---

# 3. Padrões de Camada de Serviço (`services.py`)

## 3.1. Registro de Métricas Operacionais (`RecordStopMetricService`)

A criação de métricas de paradas não deve criar múltiplos cabeçalhos de execução para a mesma viagem no mesmo dia.

Utiliza-se `get_or_create` com agrupamento por:

```text
(line, route, date)
```

```python
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import LastRouteDay, StopMetrics


class RecordStopMetricService:

    @classmethod
    @transaction.atomic
    def execute(
        cls,
        line: str,
        route: str,
        start_stop: str,
        end_stop: str,
        start_time,
        end_time
    ) -> StopMetrics:

        if start_time >= end_time:
            raise ValidationError(
                "O horário de chegada deve ser posterior ao horário de partida."
            )

        today = date.today()

        last_route_day, _ = LastRouteDay.objects.get_or_create(
            line=line,
            route=route,
            date=today,
            defaults={
                'line': line,
                'route': route,
            }
        )

        return StopMetrics.objects.create(
            last_route_day=last_route_day,
            start_stop=start_stop,
            end_stop=end_stop,
            start_time=start_time,
            end_time=end_time
        )
```

---

## 3.2. Espelhamento Automático de Rotas (`Reverse`)

Ao gerar a **Rota de Volta** a partir da **Rota de Ida**:

1. Inverter a sequência das paradas.
2. Deslocar os valores da coluna `distancia` em uma posição na lista.
3. Remapear a distância para representar corretamente os novos trechos após a inversão.

Exemplo conceitual:

```text
IDA:

P1 ──10km──> P2 ──5km──> P3
```

Após o espelhamento:

```text
VOLTA:

P3 ──5km──> P2 ──10km──> P1
```

> **Nota:** a distância pertence ao trecho entre `parada_inicio` e `parada_fim`. Portanto, ao inverter a sequência, os valores precisam ser reposicionados para continuar representando o trecho correto.

---

# 4. Regras e Indicadores Operacionais (KPIs)

## 4.1. Previsão de ETA (Estudante)

Para estimar o tempo de chegada:

1. Obter a distância `d` cadastrada em `RotaParadas` para o trecho `P_A → P_B`.
2. Obter a duração:

$$
\Delta t = end\_time - start\_time
$$

das últimas execuções cadastradas em `StopMetrics` para esse mesmo trecho.
3. Derivar a velocidade média:

$$
v = \frac{d}{\Delta t}
$$

4. Utilizar a velocidade obtida para projetar o tempo restante de chegada do veículo.

---

## 4.2. Lotação e Ocupação (Gestor)

A demanda pode ser mensurada agrupando os registros de `StudentsUsingBus` por rota e dia:

```python
StudentsUsingBus.objects.filter(
    route=rota,
    day=data
).count()
```

Esse valor poderá ser utilizado para mensurar a demanda em relação à capacidade máxima do veículo.

---

## 4.3. Validação de Município

Operações de consulta e escrita devem validar o escopo da rede escolar/município associado ao usuário gestor.

O gestor não deve conseguir acessar ou associar recursos que estejam fora do seu escopo de atendimento.

---

# 5. Diretrizes para Agentes de IA / Desenvolvedores

## Não desnormalizar sem necessidade explícita

Nunca adicionar colunas redundantes em modelos filhos quando os mesmos dados puderem ser recuperados através de uma `ForeignKey` ou `@property`.

Exemplo:

```text
LastRouteDay
├── line
└── route
    │
    └── StopMetrics
```

Nesse cenário, `StopMetrics` não deve replicar `line` e `route`.

---

## Respeitar os `related_name`

Ao conectar múltiplas `ForeignKey`s para o mesmo model, como:

```python
parada_inicio = models.ForeignKey('Parada', ...)
parada_fim = models.ForeignKey('Parada', ...)
```

sempre especificar `related_name` distintos para evitar conflitos no relacionamento reverso do ORM:

```python
parada_inicio = models.ForeignKey(
    'Parada',
    related_name='trechos_origem',
    ...
)

parada_fim = models.ForeignKey(
    'Parada',
    related_name='trechos_destino',
    ...
)
```

---

## Manter Constraints Rígidas

Garantir que constraints de unicidade sejam mantidas no `Meta` dos models para evitar duplicidade de dados, inclusive em situações de retry do cliente.

Preferir `UniqueConstraint` para novas implementações:

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=['rota', 'ordem'],
            name='unique_rota_ordem'
        )
    ]
```

`unique_together` deve ser mantido apenas onde já fizer parte de uma implementação existente ou quando houver uma razão de compatibilidade.

---

# Princípios Gerais

1. **Models:** representam dados e integridade estrutural.
2. **Services:** concentram regras de negócio e orquestração.
3. **Views/Serializers:** recebem dados, validam aspectos de entrada e delegam a operação.
4. **Banco:** garante integridade através de constraints e relacionamentos.
5. **Transações:** operações compostas devem ser atômicas.
6. **Dados derivados:** devem ser calculados quando necessário, evitando persistência redundante.
7. **Escopo:** toda operação deve respeitar município/rede de atendimento do gestor.
8. **Rotas:** a distância pertence ao trecho entre duas paradas, e o espelhamento deve preservar essa semântica.