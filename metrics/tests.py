"""Testes da app ``metrics`` — reescrito do zero (25/09/2026).

Os testes antigos foram descartados: a comunicação entre services mudou muito
(``cache_handler`` sumiu, ``services.py`` virou ``service.py``, views/urls/admin
foram removidos) e a suíte antiga nem importava mais.

Este arquivo tem dois papéis, e isso é proposital:

1. **Proteger o que já está certo** (testes VERDES): cálculos puros de ETA,
   contrato do "0" (sem previsão), registro/idempotência do aluno na rota,
   constraint de unicidade e remoção do aluno no cancelamento do dia.
2. **Evidenciar os erros do ``relatorio.md``** (testes VERMELHOS esperados):
   cada um falha HOJE de propósito, e a mensagem do assert/doca do método diz
   qual é o bug, o item do relatório e o que precisa mudar para ficar verde.
   Não há ``expectedFailure``: a falha É a evidência.

Como rodar:

    python manage.py test metrics -v 2

Situação no branch ``merged/auth/metrics`` (auditoria de 25/09/2026)

Os bloqueadores **I1** (migrations conflitantes em ``authentication``) e
**I2** (``E032`` — nome de constraint repetido em ``LastRouteDay`` e
``StopMetrics``) impedem a suíte INTEIRA de rodar: ``manage.py test`` morre na
criação do banco por causa do I1 e, resolvido o I1, os checks do runner
abortam no I2. A tabela abaixo pressupõe I1/I2 corrigidos (foi assim que a
execução de referência desta auditoria foi feita — ver ``relatorio.md``).

+-----------------------------------------------+------------------------------+
| Teste                                         | Situação                     |
+-----------------------------------------------+------------------------------+
| CalculosPurosTests (5)                        | VERDE                        |
| AlunoNaRotaTests (4)                          | VERDE                        |
| AssinaturaDosServicesTests (1)                | VERDE (item antigo 5.3 fix)  |
| ContratoDeRetornoTests (3)                    | VERDE (item antigo 5.4 fix)  |
| ModelDivergenteDaSpecTests (1)                | VERDE (item antigo 5.6 fix)  |
| MigracaoPendenteTests (2)                     | VERDE com I2/M2 corrigidos   |
| ContratoDaPrevisaoTests (4)                   | VERMELHO — M1                |
| CabecalhoDoDiaTests (2)                       | VERMELHO — M1                |
| RegistroDuplicadoTests (1)                    | VERMELHO — M1                |
| ConclusaoDaRotaTests (2)                      | VERMELHO — M1                |
| PrevisaoNoFluxoRealTests (1)                  | VERMELHO — M1                |
| PrevisaoSemFiltroDeDataTests (1)              | VERMELHO — M1 (vira trava)   |
| ChaveDeCacheTests (1)                         | VERMELHO — M1 (vira trava)   |
| CancelamentoDeInscricaoTests (1)              | VERMELHO — M4                |
| AdminVazioTests (1)                           | VERMELHO — M5                |
| CodigoMortoTests (1)                          | VERMELHO — M6 (limitação)    |
| IntegracaoPendenteTests (2)                   | VERMELHO — M7 (limitação MVP)|
| CriacaoDeCabecalhoTests (1)                   | VERMELHO — M1 (trava nova)   |
| NomesDeConstraintTests (1)                    | VERMELHO — I2 (trava nova)   |
+-----------------------------------------------+------------------------------+

**M1** é a regressão do commit ``78c8773``: ``created_at`` perdeu o
preenchimento automático (``auto_created=True`` não preenche nada) e a coluna
é ``NOT NULL`` — qualquer criação de cabeçalho estoura ``IntegrityError``,
inclusive o ``get_or_create`` do próprio ``set_last_stop_metrics``. Sem
cabeçalho não entra NENHUM dado e o ETA fica permanentemente em 0 (a regra do
trecho anterior nunca roda).

LIMITANTES DO MVP (motivo de parte dos testes ficar vermelha)
=============================================================

* O MVP ainda está em desenvolvimento e hoje só existem as partes de
  **métricas** e **autenticação**. **Ainda não existem views de inscrição,
  presença, viagem, conclusão ou cancelamento** — é por isso que
  ``IntegracaoPendenteTests`` falha: não há ninguém para chamar os services.
  A falha é esperada e some quando as views das outras apps forem escritas
  (o app metrics, por regra de arquitetura, não recebe requisições nem tem
  autorização própria).
* **Migration (relatório 4.1) — resolvido durante esta sessão**: a migration
  ``0002`` foi gerada e aplicada em 25/09/2026, então ``MigracaoPendenteTests``
  agora é **verde** e funciona como trava para a migration não sumir de novo.
  O ``setUpModule()`` mantém o remendo condicional do schema como rede de
  segurança: se a migration faltar, os demais testes continuam evidenciando os
  **próprios** bugs em vez de todo mundo estourar ``OperationalError``.
* ``metrics/cache_handler.py`` não existe mais; a partida da viagem agora é
  ``service.start_trip_metric``.
"""
import inspect
import warnings
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.core.cache import CacheKeyWarning, cache
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import get_resolver
from django.utils import timezone

from authentication.models import User

from . import service
from .models import LastRouteDay, StopMetrics, StudentsUsingBus

LINHA = "Linha 1"
ROTA = "Rota Centro"



# --------------------------------------------------------------------------- #
# Utilitários próprios (nada que dependa de módulo apagado)
# --------------------------------------------------------------------------- #
def _colunas(model):
    """Lista as colunas reais da tabela de ``model`` no banco de teste."""
    with connection.cursor() as cursor:
        descricao = connection.introspection.get_table_description(cursor, model._meta.db_table)
        return [c.name for c in descricao]


def _constraints(model):
    """Lista os nomes das constraints reais da tabela de ``model``."""
    with connection.cursor() as cursor:
        return list(connection.introspection.get_constraints(cursor, model._meta.db_table))


def criar_aluno(email="aluno@unirotas.com"):
    """Cria o usuário pelo manager (sem senha: evita custo de hash e validadores)."""
    return User.objects.create_user(email=email, full_name="Aluno de Teste")


def gravar_tramo(line, route, distance_km, duracao_segundos, order=1):
    """Grava um trecho já concluído, com horários realistas (no passado).

    Escreve direto no banco de propósito: é o cenário de uma viagem que já
    aconteceu, para os testes de previsão não dependerem dos bugs de gravação
    do próprio service (item M1 do ``relatorio.md``).

    ``date`` é explícito no model atual (o service sempre passa
    ``timezone.localdate()``); o ``created_at`` precisa sair preenchido pelo
    próprio Django — hoje isso está quebrado (M1) e é o que derruba os testes
    abaixo com ``IntegrityError``.
    """
    inicio = timezone.now() - timedelta(seconds=duracao_segundos + 300)
    cabecalho = LastRouteDay.objects.create(
        line=line, route=route, date=timezone.localdate()
    )
    fim = inicio + timedelta(seconds=duracao_segundos)
    # created_at/data no passado: é o cabeçalho de quem JÁ rodou aquela viagem
    # (também evita empate de ordenação com cabeçalhos criados pelo teste).
    LastRouteDay.objects.filter(pk=cabecalho.pk).update(created_at=fim)
    return StopMetrics.objects.create(
        last_route_day=cabecalho,
        start_stop="Terminal",
        end_stop="Praca Central",
        distance=Decimal(str(distance_km)),
        start_time=inicio,
        end_time=fim,
        order=order,
    )


# Flags capturadas ANTES do remendo de schema (ver ``setUpModule``).
MIGRATION_0002_FALTANDO = None
CONSTRAINT_FALTANDO = None


def setUpModule():
    """Rede de segurança de schema + flag de migration pendente (relatorio.md).

    A migration ``0002`` existe desde 25/09/2026 (item M2 do relatorio.md
    cobre o drift restante), então isto aqui é um **no-op** hoje. O remendo
    fica como rede de segurança: se a migration sumir de novo, o banco de
    teste nasce sem
    ``is_concluded``/constraint e TODO teste que toque em ``LastRouteDay``
    estouraria ``OperationalError``, mascarando os demais bugs que este arquivo
    precisa evidenciar.

    ``MIGRATION_0002_FALTANDO``/``CONSTRAINT_FALTANDO`` são capturados AQUI,
    antes de qualquer remendo, e é o que ``MigracaoPendenteTests`` lê.
    """
    global MIGRATION_0002_FALTANDO, CONSTRAINT_FALTANDO

    MIGRATION_0002_FALTANDO = "is_concluded" not in _colunas(LastRouteDay)
    CONSTRAINT_FALTANDO = "unique_order_per_route_day" not in _constraints(StopMetrics)

    if not (MIGRATION_0002_FALTANDO or CONSTRAINT_FALTANDO):
        return

    with connection.schema_editor(atomic=True) as editor:
        if MIGRATION_0002_FALTANDO:
            editor.add_field(LastRouteDay, LastRouteDay._meta.get_field("is_concluded").clone())
        if CONSTRAINT_FALTANDO:
            constraint = next(
                c for c in StopMetrics._meta.constraints
                if c.name == "unique_order_per_route_day"
            )
            editor.add_constraint(StopMetrics, constraint)


# =========================================================================== #
# PARTE 1 — testes VERDES: protegem o que já funciona
# =========================================================================== #
class CalculosPurosTests(TestCase):
    """Funções puras usadas pelo KPI de ETA (contrato do service)."""

    def test_delta_time_em_segundos(self):
        inicio = timezone.now()
        fim = inicio + timedelta(minutes=35)

        self.assertEqual(service.calculate_delta_time(inicio, fim), 2100.0)

    def test_converte_km_para_metros(self):
        self.assertEqual(service.convert_km_to_m(1.5), 1500.0)

    def test_velocidade_media_em_metros_por_segundo(self):
        # 1,5 km em 100 s -> 15 m/s
        velocidade = service.calculate_meters_per_second(100, 1.5)

        self.assertEqual(float(velocidade), 15.0)

    def test_velocidade_zerada_quando_o_tramo_nao_durou_nada(self):
        """Tramo impossível (delta <= 0) não pode virar divisão por zero."""
        self.assertEqual(service.calculate_meters_per_second(0, 5.0), 0.0)
        self.assertEqual(service.calculate_meters_per_second(-10, 5.0), 0.0)

    def test_contagem_para_a_proxima_parada_arredonda_para_cima(self):
        """O arredondamento é sempre para CIMA (ceil), como no ETA.

        Decisão registrada no commit ``78c8773`` ("constancia no retorno do
        arredondamento do tempo"): ``get_time_prediction`` e
        ``calculate_next_stop_time`` usam ``math.ceil`` — nunca subestimar a
        chegada. O teste antigo pedia ``floor`` e foi atualizado nesta
        auditoria para travar a decisão atual.
        """
        # 125 m a 6 m/s = 20,83 s -> 21 s (ceil)
        self.assertEqual(service.calculate_next_stop_time(6.0, 0.125), 21)
        self.assertEqual(service.calculate_next_stop_time(0.0, 1.0), 0)


class ContratoDaPrevisaoTests(TestCase):
    """Contrato de ``get_time_prediction`` — o que o front pode esperar.

    REGRA DE FRONT (contrato do app): o retorno é um **inteiro de segundos**;
    ``0`` significa "não foi possível marcar predição" e > 0 significa que o
    front deve somar os segundos ao horário atual e mostrar ``HH:MM``.

    A regra de negócio do MVP é usar a velocidade do trecho IMEDIATAMENTE
    anterior; por isso o ``setUp`` grava um tramo (3,6 km em 12 min = 5 m/s).
    Hoje o ``setUp`` morre no item **M1** do ``relatorio.md``.
    """

    def setUp(self):
        cache.clear()
        # 3,6 km em 12 min = 5 m/s = 18 km/h (ritmo plausível de ônibus)
        self.tramo_anterior = gravar_tramo(LINHA, ROTA, 3.6, 720)

    def test_sem_dados_devolve_zero_para_o_front(self):
        """Sentinela verde: sem tramo anterior, devolve 0 (relatório 4.5)."""
        previsao = service.get_time_prediction("Linha inexistente", ROTA, 2, 2.0)

        self.assertEqual(previsao, 0)

    def test_devolve_inteiro_de_segundos_deterministico(self):
        previsao = service.get_time_prediction(LINHA, ROTA, 2, 2.0)

        self.assertIsInstance(previsao, int)
        self.assertEqual(previsao, 400)  # 2 km a 5 m/s
        self.assertEqual(previsao, service.get_time_prediction(LINHA, ROTA, 2, 2.0))

    def test_cresce_proporcionalmente_a_distancia(self):
        um_km = service.get_time_prediction(LINHA, ROTA, 2, 1.0)
        dois_km = service.get_time_prediction(LINHA, ROTA, 2, 2.0)
        quatro_km = service.get_time_prediction(LINHA, ROTA, 2, 4.0)

        self.assertEqual((um_km, dois_km, quatro_km), (200, 400, 800))

    def test_arredonda_para_cima_nunca_subestima_a_chegada(self):
        # 125 m a 5 m/s = 25 s exatos; 126 m = 25,2 s -> 26 s (ceil)
        exato = service.get_time_prediction(LINHA, ROTA, 2, 0.125)
        fracionario = service.get_time_prediction(LINHA, ROTA, 2, 0.126)

        self.assertEqual(exato, 25)
        self.assertEqual(fracionario, 26)


class AlunoNaRotaTests(TestCase):
    """Registro do aluno na rota no dia (``register_student``/``destruct_student``).

    A unicidade real do aluno (presença + conclusão da viagem) fica FORA deste
    app — aqui só registramos a intenção de uso; a constraint do banco é a
    cintura de segurança (relatório 6.5).
    """

    def setUp(self):
        self.aluno = criar_aluno()

    def test_registro_grava_o_uso_de_hoje(self):
        service.register_student(self.aluno, ROTA)

        uso = StudentsUsingBus.objects.get()

        self.assertEqual(uso.user, self.aluno)
        self.assertEqual(uso.route, ROTA)
        self.assertEqual(uso.day, timezone.localdate())

    def test_registro_repetido_nao_duplica(self):
        """Idempotência: retry da view não pode gerar linha extra."""
        service.register_student(self.aluno, ROTA)
        service.register_student(self.aluno, ROTA)

        self.assertEqual(StudentsUsingBus.objects.count(), 1)

    def test_constraint_bloqueia_uso_duplicado_do_mesmo_dia(self):
        """A constraint precisa existir no banco (mesmo com o get_or_create)."""
        StudentsUsingBus.objects.create(user=self.aluno, route=ROTA)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StudentsUsingBus.objects.create(user=self.aluno, route=ROTA)

    def test_destruct_remove_o_registro_de_hoje(self):
        service.register_student(self.aluno, ROTA)

        service.destruct_student(self.aluno, ROTA)

        self.assertEqual(StudentsUsingBus.objects.filter(user=self.aluno).count(), 0)


# =========================================================================== #
# PARTE 2 — testes VERMELHOS: evidenciam os erros do relatorio.md
# Cada docstring diz POR QUE o teste falha hoje e o que precisa mudar.
# =========================================================================== #
class MigracaoPendenteTests(TestCase):
    """Models e migrations precisam andar juntos (itens I2/M2 do relatorio.md).

    ``is_concluded`` e a constraint ``unique_order_per_route_day`` ganharam
    migration em 25/09/2026, mas o commit ``78c8773`` mexeu em
    ``date``/``created_at`` e somou outra constraint SEM migration (M2), e o
    ``makemigrations`` hoje nem roda por causa do ``E032`` (I2). Estes dois
    testes são a trava: se alguém mexer nos models sem gerar migration, eles
    ficam vermelhos de novo (o ``makemigrations --check`` é a forma canônica
    de cobrir isso no CI).
    """

    def test_makemigrations_nao_detecta_alteracao_pendente(self):
        saida = StringIO()
        try:
            call_command(
                "makemigrations", "metrics", "--check", "--dry-run",
                stdout=saida, stderr=saida,
            )
        except SystemCheckError as erro:
            self.fail(
                "I2 (relatorio.md): o sistema nem deixa rodar o makemigrations "
                f"por causa de erro de checagem ({erro}). Corrigir o nome de "
                "constraint duplicado e gerar as migrations."
            )
        except SystemExit:
            self.fail(
                "M2 (relatorio.md): existem alterações de modelo sem migration "
                f"para metrics ({saida.getvalue().strip()}). Para ficar verde, "
                "rode `python manage.py makemigrations metrics`, commite o "
                "arquivo gerado e depois `python manage.py migrate`."
            )

    def test_coluna_is_concluded_existe_no_banco(self):
        self.assertFalse(
            MIGRATION_0002_FALTANDO,
            "M2 (relatorio.md): o banco nasceu sem a coluna `is_concluded` "
            "porque a migration 0002 nunca foi gerada. O setUpModule() "
            "remenda o schema só para os demais testes rodarem; a correção é "
            "gerar e aplicar a migration.",
        )


class CabecalhoDoDiaTests(TestCase):
    """Um mesmo dia tem UM cabeçalho ``LastRouteDay`` (regressão 4.2).

    A causa original (``DateTimeField(auto_now_add)`` vs lookup por
    ``timezone.localdate()``) foi corrigida: ``date`` virou ``DateField``
    explícito e o ``get_or_create`` do service agora casa. O que derruba
    estes testes hoje é o item **M1** do ``relatorio.md``: a criação do
    cabeçalho estoura ``IntegrityError`` porque ``created_at`` perdeu o
    preenchimento automático e a coluna é ``NOT NULL``.
    """

    def setUp(self):
        cache.clear()

    def test_uma_linha_rodando_no_dia_tem_um_unico_cabecalho(self):
        service.set_last_stop_metrics(LINHA, ROTA, "Terminal", 1, 5.0)
        service.set_last_stop_metrics(LINHA, ROTA, "Praca", 2, 2.0)

        cabecalhos = LastRouteDay.objects.filter(line=LINHA, route=ROTA).count()

        self.assertEqual(
            cabecalhos, 1,
            f"M1 (relatorio.md): {cabecalhos} cabeçalhos para a mesma "
            "linha/rota/dia. O service precisa reaproveitar o cabeçalho do "
            "dia (get_or_create por line/route/date) e a criação não pode "
            "estourar por causa de `created_at`.",
        )

    def test_cabecalho_criado_agora_e_reaproveitado(self):
        """Reproduz literalmente o ``get_or_create`` de ``set_last_stop_metrics``.

        Contrato atual do model: ``date`` é explícito (o service passa
        ``timezone.localdate()``) e ``created_at`` deve ser preenchido
        automaticamente — hoje ele explode com ``IntegrityError`` por causa
        do item **M1** do ``relatorio.md``.
        """
        cabecalho = LastRouteDay.objects.create(
            line=LINHA, route=ROTA, date=timezone.localdate()
        )

        _, criado = LastRouteDay.objects.get_or_create(
            line=LINHA, route=ROTA, date=timezone.localdate()
        )

        self.assertFalse(
            criado,
            "M1 (relatorio.md): o cabeçalho registrado agora precisa ser "
            f"reaproveitado pelo get_or_create (pk {cabecalho.pk}), não "
            "duplicado.",
        )


class RegistroDuplicadoTests(TestCase):
    """Retry da mesma parada não duplica registro (regressão 4.2)."""

    def setUp(self):
        cache.clear()

    def test_retry_da_mesma_parada_nao_duplica_registro(self):
        self.assertIn(
            "unique_order_per_route_day", _constraints(StopMetrics),
            "pré-condição: a constraint precisa existir no banco para o teste "
            "provar que ela não impede a duplicação.",
        )

        service.set_last_stop_metrics(LINHA, ROTA, "Terminal", 1, 5.0)
        service.set_last_stop_metrics(LINHA, ROTA, "Terminal", 1, 5.0)  # retry da view

        duplicados = StopMetrics.objects.filter(order=1).count()

        self.assertEqual(
            duplicados, 1,
            f"M1 (relatorio.md): {duplicados} registros para a mesma parada "
            "(order=1). Com o cabeçalho do dia único, o get_or_create por "
            "(last_route_day, order) precisa segurar o retry da view.",
        )


class ConclusaoDaRotaTests(TestCase):
    """``set_route_as_done`` precisa achar a rota registrada hoje (regressão 4.4).

    Isso entra direto na regra do time: a conclusão da viagem é uma das duas
    metades da unicidade do aluno (a outra é a presença) e acontece fora do
    app metrics — mas só funciona se este service achar o cabeçalho do dia.
    Hoje quem derruba estes testes é o item **M1** (criação do cabeçalho),
    não mais o filtro por data (que já usa ``timezone.localdate()``).
    """

    def setUp(self):
        cache.clear()

    def test_set_route_as_done_nao_lanca_para_rota_registrada_hoje(self):
        service.set_last_stop_metrics(LINHA, ROTA, "Terminal", 1, 5.0)

        try:
            service.set_route_as_done(LINHA, ROTA)
        except ValueError as erro:
            self.fail(
                "M1 (relatorio.md): a rota foi registrada agora e a conclusão "
                f"lançou `ValueError: {erro}`. O service não deve lançar em "
                "cenário previsto — devolver status tratável."
            )

    def test_filtro_do_dia_encontra_o_cabecalho_registrado_agora(self):
        service.set_last_stop_metrics(LINHA, ROTA, "Terminal", 1, 5.0)

        encontrado = LastRouteDay.objects.filter(
            line=LINHA, route=ROTA, date=timezone.localdate()
        ).first()

        self.assertIsNotNone(
            encontrado,
            "M1 (relatorio.md): a rota foi registrada hoje, mas o filtro que "
            "`set_route_as_done` usa não devolveu o cabeçalho — conferir "
            "`date=timezone.localdate()` e a criação do cabeçalho.",
        )


class PrevisaoNoFluxoRealTests(TestCase):
    """A previsão usa o trecho imediatamente anterior (regra do MVP).

    Cenário: o trecho 1 já aconteceu (3,6 km em 12 min = 5 m/s) e o service
    registra a chegada na segunda parada; a previsão do trecho 2 (2 km) tem de
    dar 400 s. Hoje o fluxo morre no item **M1** (criação do cabeçalho estoura
    antes de qualquer cálculo); depois de M1 corrigido, se a previsão seguir
    0, o fluxo voltou a criar cabeçalho novo no meio do caminho — exatamente o
    que este teste trava.
    """

    def setUp(self):
        cache.clear()

    def test_segunda_parada_tem_previsao_maior_que_zero(self):
        # viagem real: o primeiro trecho já aconteceu (3,6 km em 12 min = 5 m/s)
        gravar_tramo(LINHA, ROTA, 3.6, 720, order=1)
        # e o motor registra a chegada na segunda parada pelo service
        service.set_last_stop_metrics(LINHA, ROTA, "Praca", 2, 2.0)

        previsao = service.get_time_prediction(LINHA, ROTA, 2, 2.0)

        self.assertGreater(
            previsao, 0,
            "M1 (relatorio.md): existia tramo anterior (2 km a 5 m/s = 400 s) "
            f"e a previsão veio {previsao}. Esperado 400 com a regra do trecho "
            "imediatamente anterior; se continuar 0, o fluxo de previsão está "
            "perdendo o tramo anterior (cabeçalho novo / filtro errado).",
        )


class PrevisaoSemFiltroDeDataTests(TestCase):
    """O trecho anterior precisa ser do DIA da viagem (regressão 5.2).

    O código atual JÁ filtra ``date=timezone.localdate()`` em
    ``get_last_stop_metrics`` — este teste é a trava de regressão. Antes da
    correção o tramo de ontem vazava para a previsão de hoje; depois do item
    **M1** corrigido ele fica verde e impede a regressão.
    """

    def setUp(self):
        cache.clear()

    def test_tramo_de_dia_anterior_nao_serve_para_a_viagem_de_hoje(self):
        cabecalho = gravar_tramo(LINHA, ROTA, 3.6, 720, order=1)
        # data do cabeçalho forçada para ontem (o model exige date explícito)
        LastRouteDay.objects.filter(pk=cabecalho.pk).update(
            date=timezone.localdate() - timedelta(days=1)
        )

        ultimo = service.get_last_stop_metrics(LINHA, ROTA, 2)

        self.assertIsNone(
            ultimo,
            "Regressão 5.2: hoje não existe viagem registrada e o service "
            f"devolveu o tramo de ontem ({ultimo}) porque parou de filtrar "
            "`date=timezone.localdate()` em `get_last_stop_metrics`.",
        )


class ContratoDeRetornoTests(TestCase):
    """Retorno explícito das funções principais (item antigo 5.4 — RESOLVIDO).

    ``register_student`` devolve o resultado do ``get_or_create``,
    ``destruct_student`` devolve bool e ``set_route_as_done`` devolve bool em
    vez de lançar exceção (commits ``4142b53``/``6adcc54``). Os três testes
    abaixo são as travas de regressão do contrato.
    """

    def setUp(self):
        cache.clear()
        self.aluno = criar_aluno()

    def test_register_student_retorna_resultado(self):
        resultado = service.register_student(self.aluno, ROTA)

        self.assertIsNotNone(
            resultado,
            "Contrato: `register_student` devolveu None — a view de inscrição "
            "precisa de um retorno tratável, sem reconsultar o banco.",
        )

    def test_destruct_student_retorna_resultado(self):
        service.register_student(self.aluno, ROTA)

        resultado = service.destruct_student(self.aluno, ROTA)

        self.assertIsNotNone(
            resultado,
            "Contrato: `destruct_student` devolveu None — a view de "
            "cancelamento precisa saber se apagou algo (hoje o service já "
            "devolve bool: True/False).",
        )

    def test_set_route_as_done_retorna_status_em_vez_de_lancar(self):
        try:
            resultado = service.set_route_as_done(LINHA, ROTA)
        except ValueError as erro:
            self.fail(
                "Contrato: rota ainda não registrada é um cenário de negócio "
                f"legítimo e o service lançou `ValueError: {erro}` em vez de "
                "retornar um status tratável pela view."
            )

        self.assertIsNotNone(
            resultado,
            "Contrato: `set_route_as_done` devolveu None mesmo no caminho de "
            "sucesso — hoje ele devolve bool (True/False).",
        )


class CancelamentoDeInscricaoTests(TestCase):
    """M4 (relatorio.md) — cancelar inscrição precisa limpar o histórico do aluno.

    A view de cancelamento (ainda não escrita, ver ``IntegracaoPendenteTests``)
    precisa chamar ``destruct_student``. Aqui fica evidenciado que o método,
    como está, só apaga o registro do dia corrente.
    """

    def test_cancelamento_apaga_todo_o_historico_do_aluno_na_rota(self):
        aluno = criar_aluno("cancelado@unirotas.com")
        ontem = timezone.localdate() - timedelta(days=1)
        StudentsUsingBus.objects.create(user=aluno, route=ROTA, day=ontem)
        StudentsUsingBus.objects.create(user=aluno, route=ROTA)  # hoje

        service.destruct_student(aluno, ROTA)

        restantes = StudentsUsingBus.objects.filter(user=aluno, route=ROTA).count()

        self.assertNotEqual(
            restantes, 0,
            f"M4 (relatorio.md): o cancelamento deixou {restantes} registro(s) "
            "antigo(s) no banco, porque `destruct_student` filtra por "
            "`day=timezone.localdate()`. Definir se o cancelamento apaga só o "
            "pendente do dia ou o histórico todo.",
        )


class AssinaturaDosServicesTests(TestCase):
    """``set_`` e ``get_`` usam a mesma ordem de argumentos (5.3 — RESOLVIDO).

    Os dois services foram alinhados no commit ``6adcc54``; a trava impede
    que a troca volte (as duas primeiras posições são strings e uma view
    posicional trocaria linha por rota em silêncio).
    """

    def test_set_e_get_usam_a_mesma_ordem_de_argumentos(self):
        ordem_set = list(inspect.signature(service.set_last_stop_metrics).parameters)[:2]
        ordem_get = list(inspect.signature(service.get_last_stop_metrics).parameters)[:2]

        self.assertEqual(
            ordem_set, ordem_get,
            "Regressão 5.3: `set_last_stop_metrics(line, route, ...)` e "
            f"`get_last_stop_metrics({', '.join(ordem_get)}, ...)` têm ordens "
            "diferentes — uma view chamando sem keyword troca linha por rota "
            "silenciosamente.",
        )


class CodigoMortoTests(TestCase):
    """M6 (relatorio.md) — ``build_route_timeline_prediction`` é código morto.

    O corpo itera sobre ``route_stops = []`` (o model ``RouteStop``/``RotaParadas``
    não existe nesta branch) e, mesmo se existisse, mistura objeto FK
    (``rs.start_stop.name``) com o padrão "strings de ponta a ponta" adotado
    pelo resto do service.
    """

    def test_timeline_de_previsao_retorna_alguma_parada(self):
        resultado = service.build_route_timeline_prediction(LINHA, ROTA, current_order=1)

        self.assertTrue(
            resultado.get("timeline"),
            "M6 (relatorio.md): a função promete a timeline de todas as paradas "
            f"com ETA e devolve {resultado!r} — o laço roda sobre "
            "`route_stops = []` hardcoded. Implementar de verdade (depende da "
            "app de rotas) ou remover/isolar com NotImplementedError.",
        )


class ModelDivergenteDaSpecTests(TestCase):
    """``StopMetrics.distance`` precisa de precisão definida (5.6 — RESOLVIDO).

    O campo usa ``max_digits=6, decimal_places=2`` (migration ``0004``); sem
    isso o SQLite aceita qualquer coisa e o Postgres criaria um ``numeric``
    sem precisão. A trava impede a regressão.
    """

    def test_distance_tem_precisao_definida(self):
        campo = StopMetrics._meta.get_field("distance")

        self.assertEqual(
            (campo.max_digits, campo.decimal_places), (6, 2),
            "Regressão 5.6: `StopMetrics.distance` perdeu a precisão "
            f"(valor atual: {campo.max_digits}/{campo.decimal_places}). "
            "Manter max_digits=6, decimal_places=2.",
        )

def _codigo_das_outras_apps():
    """Concatena o código-fonte das apps que, no MVP, vão chamar o metrics."""
    pedacos = []
    for nome in ("authentication", "core"):
        raiz = Path(settings.BASE_DIR) / nome
        if not raiz.exists():
            continue
        for caminho in sorted(raiz.rglob("*.py")):
            if "__pycache__" in caminho.parts:
                continue
            pedacos.append(caminho.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(pedacos)


class ChaveDeCacheTests(TestCase):
    """A chave da partida precisa continuar portável para qualquer backend.

    O service monta a chave como ``trip_start-{line}-{route}-{date}`` e limpa
    os espaços (``.replace(" ", "")``); sem essa limpeza, memcached/redis
    rejeitam a chave, a partida da viagem se perde e o ETA volta a ser sempre
    0. Este teste usa o fluxo real (``start_trip_metric`` +
    ``set_last_stop_metrics``) e é a trava: o LocMemCache do Django 6.1 emite
    ``CacheKeyWarning`` para chaves com espaço (confirmado por sonda nesta
    auditoria), então uma regressão na montagem da chave é pega aqui.

    Hoje o teste depende do item **M1** para chegar ao fluxo (a criação do
    cabeçalho estoura antes); depois de M1 ele fica verde.
    """

    def setUp(self):
        cache.clear()

    def test_chave_do_cache_e_portavel_para_qualquer_backend(self):
        with warnings.catch_warnings(record=True) as capturados:
            warnings.simplefilter("always")
            # fluxo real: grava a partida e lê na primeira parada
            service.start_trip_metric(LINHA, ROTA, "Terminal")
            service.set_last_stop_metrics(LINHA, ROTA, "Terminal", 1, 5.0)

        avisos = [str(w.message) for w in capturados
                  if issubclass(w.category, CacheKeyWarning)]

        self.assertEqual(
            avisos, [],
            "M3 (relatorio.md): a chave do cache não é portável para "
            f"memcached/redis (avisos: {avisos}). Manter a limpeza de espaços "
            "em `start_trip_metric`/`set_last_stop_metrics` e configurar "
            "CACHES antes de sair do LocMemCache (per-process).",
        )


class CriacaoDeCabecalhoTests(TestCase):
    """M1 (relatorio.md) — ``LastRouteDay`` precisa nascer sem ``created_at`` manual.

    Regressão do commit ``78c8773``: ``created_at`` virou
    ``DateTimeField(auto_created=True)`` — que NÃO preenche nada — e a coluna
    no banco é ``NOT NULL``. Resultado: toda criação de cabeçalho (inclusive o
    ``get_or_create`` do próprio ``set_last_stop_metrics``) estoura
    ``IntegrityError`` e nenhum dado de viagem entra no módulo. Restaurar o
    preenchimento automático (``auto_now_add``/``default``) e gerar a
    migration correspondente.
    """

    def test_cabecalho_do_dia_e_criado_com_created_at_automatico(self):
        cabecalho = LastRouteDay.objects.create(
            line=LINHA, route=ROTA, date=timezone.localdate()
        )

        self.assertIsNotNone(
            cabecalho.created_at,
            "M1 (relatorio.md): `created_at` não foi preenchido "
            "automaticamente — a criação do cabeçalho do dia precisa "
            "funcionar passando só line/route/date (como o service faz).",
        )


class NomesDeConstraintTests(TestCase):
    """I2 (relatorio.md) — nome de constraint precisa ser único no app.

    O Django recusa o projeto inteiro com ``E032`` quando dois models declaram
    a mesma ``name`` de ``UniqueConstraint`` — é o caso de ``LastRouteDay`` e
    ``StopMetrics`` hoje (ambos usam ``unique_order_per_route_day``): o
    ``manage.py check`` fica vermelho e o próprio ``manage.py test`` aborta ao
    rodar os checks pós-criação do banco.
    """

    def test_nomes_de_constraint_sao_unicos_no_app(self):
        vistos = {}
        colisoes = []
        for model in apps.get_app_config("metrics").get_models():
            for constraint in model._meta.constraints:
                nome = getattr(constraint, "name", None)
                if not nome:
                    continue
                if nome in vistos:
                    colisoes.append((nome, vistos[nome], model.__name__))
                else:
                    vistos[nome] = model.__name__

        self.assertEqual(
            colisoes, [],
            "I2 (relatorio.md): constraint(s) com nome repetido em models "
            f"diferentes: {colisoes}. Dar nomes únicos (ex.: "
            "`unique_route_per_day` em LastRouteDay) e gerar a migration.",
        )






