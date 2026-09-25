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

Situação atual esperada: parte verde, parte vermelha (tabela abaixo).

+-----------------------------------------------+------------------+
| Teste                                         | Situação         |
+-----------------------------------------------+------------------+
| CalculosPurosTests (5)                        | VERDE            |
| ContratoDaPrevisaoTests (4)                   | VERDE            |
| AlunoNaRotaTests (4)                          | VERDE            |
| MigracaoPendenteTests (2)                     | VERDE - 4.1 (fix)|
| CabecalhoDoDiaTests (2)                       | VERMELHO - 4.2   |
| RegistroDuplicadoTests (1)                    | VERMELHO - 4.2   |
| ConclusaoDaRotaTests (2)                      | VERMELHO - 4.4   |
| PrevisaoNoFluxoRealTests (1)                  | VERMELHO - 4.3   |
| PrevisaoSemFiltroDeDataTests (1)              | VERMELHO - 5.2   |
| ContratoDeRetornoTests (3)                    | VERMELHO - 5.4   |
| CancelamentoDeInscricaoTests (1)              | VERMELHO - 5.5   |
| AssinaturaDosServicesTests (1)                | VERMELHO - 5.3   |
| CodigoMortoTests (1)                          | VERMELHO - 5.7   |
| ModelDivergenteDaSpecTests (1)                | VERMELHO - 5.6   |
| AdminVazioTests (1)                           | VERMELHO - 5.8   |
| IntegracaoPendenteTests (2)                   | VERMELHO - 4.6   |
| ChaveDeCacheTests (1)                         | VERMELHO - extra |
+-----------------------------------------------+------------------+

Contagem da execução atual: **33 testes — 15 verdes, 18 vermelhos** (0 erros
de execução). Cada vermelho corresponde a um item do ``relatorio.md``.
"(fix)" = o item 4.1 foi corrigido durante esta sessão (migration ``0002``
gerada e aplicada em 25/09/2026) e os dois testes passaram a ser a trava de
regressão.

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

from django.conf import settings
from django.contrib import admin
from django.core.cache import CacheKeyWarning, cache
from django.core.management import call_command
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
    do próprio service (relatório 4.2/4.3).
    """
    inicio = timezone.now() - timedelta(seconds=duracao_segundos + 300)
    cabecalho = LastRouteDay.objects.create(line=line, route=route)
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
    """Rede de segurança de schema + flag do 4.1 (relatório).

    RELATÓRIO 4.1 (corrigido na sessão): a migration ``0002`` passou a existir
    e foi aplicada, então hoje isto aqui é um **no-op**. O remendo fica como
    rede de segurança: se a migration sumir de novo, o banco de teste nasce sem
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
    """Funções puras usadas pelo KPI de ETA (relatório 6.3)."""

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

    def test_contagem_para_a_proxima_parada_arredonda_para_baixo(self):
        # 125 m a 6 m/s = 20,83 s -> 20 s
        self.assertEqual(service.calculate_next_stop_time(6.0, 0.125), 20)
        self.assertEqual(service.calculate_next_stop_time(0.0, 1.0), 0)


class ContratoDaPrevisaoTests(TestCase):
    """Contrato de ``get_time_prediction`` — o que o front pode esperar.

    REGRA DE FRONT (relatório 3/9.1): o retorno é um **inteiro de segundos**;
    ``0`` significa "não foi possível marcar predição" e > 0 significa que o
    front deve somar os segundos ao horário atual e mostrar ``HH:MM``.
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
    """RELATÓRIO 4.1 — a migration ``0002`` existia? (VERDE desde a sessão).

    Contexto: quando o relatório foi escrito, ``is_concluded`` e a constraint
    ``unique_order_per_route_day`` não tinham migration e o ``db.sqlite3``
    estourava ``OperationalError`` em qualquer query em ``LastRouteDay``. A
    migration foi gerada/aplicada em 25/09/2026 — estes dois testes agora são
    a trava de regressão: se alguém mexer nos models sem gerar migration, eles
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
        except SystemExit:
            self.fail(
                "BUG 4.1: existem alterações de modelo sem migration para "
                f"metrics ({saida.getvalue().strip()}). Para ficar verde, rode "
                "`python manage.py makemigrations metrics`, commite o arquivo "
                "gerado e depois `python manage.py migrate`."
            )

    def test_coluna_is_concluded_existe_no_banco(self):
        self.assertFalse(
            MIGRATION_0002_FALTANDO,
            "BUG 4.1: o banco nasceu sem a coluna `is_concluded` porque a "
            "migration 0002 nunca foi gerada (idem no db.sqlite3, relatório 4.1). "
            "O setUpModule() remenda o schema só para os demais testes "
            "rodarem; a correção é gerar e aplicar a migration.",
        )


class CabecalhoDoDiaTests(TestCase):
    """RELATÓRIO 4.2 — um mesmo dia gera N cabeçalhos ``LastRouteDay`` (VERMELHO esperado).

    Causa: ``date`` é ``DateTimeField(auto_now_add)`` (grava com hora) mas o
    service faz ``get_or_create(..., date=timezone.localdate())`` (vira
    meia-noite) — o filtro nunca casa, então cada chamada cria cabeçalho novo.
    """

    def setUp(self):
        cache.clear()

    def test_uma_linha_rodando_no_dia_tem_um_unico_cabecalho(self):
        service.set_last_stop_metrics(LINHA, ROTA, "Terminal", 1, 5.0)
        service.set_last_stop_metrics(LINHA, ROTA, "Praca", 2, 2.0)

        cabecalhos = LastRouteDay.objects.filter(line=LINHA, route=ROTA).count()

        self.assertEqual(
            cabecalhos, 1,
            f"BUG 4.2: {cabecalhos} cabeçalhos para a mesma linha/rota/dia. "
            "Cada chamada cria um LastRouteDay novo (o filtro `date=localdate()` "
            "nunca casa com o DateTimeField), o que ainda por cima anula a "
            "constraint unique_order_per_route_day. Corrigir o tipo do campo "
            "(DateField) ou o lookup (`date__date`) e somar "
            "UniqueConstraint(line, route, date).",
        )

    def test_cabecalho_criado_agora_e_reaproveitado(self):
        """Reproduz literalmente o get_or_create de ``set_last_stop_metrics``."""
        cabecalho = LastRouteDay.objects.create(line=LINHA, route=ROTA)

        _, criado = LastRouteDay.objects.get_or_create(
            line=LINHA, route=ROTA, date=timezone.localdate()
        )

        self.assertFalse(
            criado,
            "BUG 4.2 (causa raiz): o service registrou a rota AGORA e o "
            "get_or_create por `date=localdate()` criou outro cabeçalho "
            f"(pk {cabecalho.pk}) em vez de reaproveitar. Comparar DateTimeField "
            "com Date vira meia-noite e não casa — relatório 4.2.",
        )


class RegistroDuplicadoTests(TestCase):
    """RELATÓRIO 4.2 — a constraint não segura retry de parada (VERMELHO esperado)."""

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
            f"BUG 4.2: {duplicados} registros para a mesma parada (order=1). A "
            "constraint unique_order_per_route_day é por `last_route_day`, e "
            "cada retry gera um cabeçalho novo, então ela nunca é violada "
            "(relatório 4.2/4.3).",
        )


class ConclusaoDaRotaTests(TestCase):
    """RELATÓRIO 4.4 — ``set_route_as_done`` nunca encontra a rota do dia (VERMELHO esperado).

    Isso entra direto na regra do time: a conclusão da viagem é uma das duas
    metades da unicidade do aluno (a outra é a presença) e acontece fora do
    app metrics — mas só funciona se este service achar o cabeçalho do dia.
    """

    def setUp(self):
        cache.clear()

    def test_set_route_as_done_nao_lanca_para_rota_registrada_hoje(self):
        service.set_last_stop_metrics(LINHA, ROTA, "Terminal", 1, 5.0)

        try:
            service.set_route_as_done(LINHA, ROTA)
        except ValueError as erro:
            self.fail(
                "BUG 4.4: a rota foi registrada agora e a conclusão lançou "
                f"`ValueError: {erro}`. Causa: o filtro `date=localdate()` não "
                "encontra o DateTimeField gravado (relatório 4.2/4.4)."
            )

    def test_filtro_do_dia_encontra_o_cabecalho_registrado_agora(self):
        service.set_last_stop_metrics(LINHA, ROTA, "Terminal", 1, 5.0)

        encontrado = LastRouteDay.objects.filter(
            line=LINHA, route=ROTA, date=timezone.localdate()
        ).first()

        self.assertIsNotNone(
            encontrado,
            "BUG 4.4 (causa raiz): a rota foi registrada hoje, mas o filtro "
            "que `set_route_as_done` usa não devolve o cabeçalho — por isso a "
            "conclusão sempre falha com 'esta rota não foi registrada hoje'.",
        )


class PrevisaoNoFluxoRealTests(TestCase):
    """RELATÓRIO 4.3 — no fluxo real a previsão sai sempre 0 (VERMELHO esperado).

    É o teste que prova que o aluno **nunca** veria horário previsto: o
    ``set_last_stop_metrics`` cria um cabeçalho novo antes de procurar o tramo
    anterior, então ``get_last_stop_metrics`` acha um cabeçalho vazio e o ETA
    morre. É a regra de front (0 = "não foi possível marcar predição")
    escondendo um bug, não um caso de borda.
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
            "BUG 4.3: existia tramo anterior (2 km a 5 m/s = 400 s) e a "
            f"previsão veio {previsao}. O service criou um LastRouteDay novo "
            "antes de buscar o tramo anterior, então `get_last_stop_metrics` "
            "encontrou o cabeçalho recém-criado e vazio e devolveu None. "
            "Com a correção do 4.2 o retorno esperado é 400.",
        )


class PrevisaoSemFiltroDeDataTests(TestCase):
    """RELATÓRIO 5.2 — ``get_last_stop_metrics`` não filtra data nem is_concluded."""

    def setUp(self):
        cache.clear()

    def test_tramo_de_dia_anterior_nao_serva_para_a_viagem_de_hoje(self):
        cabecalho = gravar_tramo(LINHA, ROTA, 3.6, 720, order=1)
        # data do cabeçalho forçada para ontem (auto_now_add não deixa na criação)
        LastRouteDay.objects.filter(pk=cabecalho.pk).update(
            date=timezone.localdate() - timedelta(days=1)
        )

        ultimo = service.get_last_stop_metrics(ROTA, LINHA, 2)

        self.assertIsNone(
            ultimo,
            "BUG 5.2: hoje não existe viagem registrada e o service devolveu "
            f"o tramo de ontem ({ultimo}) porque filtra só por linha/rota e "
            "pega o `.first()` mais recente, sem olhar `date` nem "
            "`is_concluded`. Decisão pendente (relatório 5.2/9.3): filtrar o "
            "dia da viagem atual ou documentar que o ETA é histórico.",
        )


class ContratoDeRetornoTests(TestCase):
    """RELATÓRIO 5.4 — falta de retorno explícito nas funções principais.

    O commit ``e5e9db8`` promete "todas funções auxiliares e principais têm um
    retorno explícito para ser tratado em caso de falha", mas hoje
    ``register_student``/``destruct_student`` devolvem ``None`` e
    ``set_route_as_done`` lança exceção. Sem retorno, a view que chama o
    service (inscrição/cancelamento/conclusão) não tem como saber se deu certo.
    """

    def setUp(self):
        cache.clear()
        self.aluno = criar_aluno()

    def test_register_student_retorna_resultado(self):
        resultado = service.register_student(self.aluno, ROTA)

        self.assertIsNotNone(
            resultado,
            "BUG 5.4: `register_student` devolveu None — a view de inscrição "
            "não tem como saber se o registro aconteceu sem reconsultar o "
            "banco. Retornar algo explícito (ex.: o próprio StudentsUsingBus "
            "ou um status).",
        )

    def test_destruct_student_retorna_resultado(self):
        service.register_student(self.aluno, ROTA)

        resultado = service.destruct_student(self.aluno, ROTA)

        self.assertIsNotNone(
            resultado,
            "BUG 5.4: `destruct_student` devolveu None — a view de cancelamento "
            "de inscrição não sabe se apagou algo (e hoje, se não houver "
            "registro de hoje, ela apaga 0 linhas em silêncio).",
        )

    def test_set_route_as_done_retorna_status_em_vez_de_lancar(self):
        try:
            resultado = service.set_route_as_done(LINHA, ROTA)
        except ValueError as erro:
            self.fail(
                "BUG 5.4: rota ainda não registrada é um cenário de negócio "
                f"legítimo e o service lançou `ValueError: {erro}` em vez de "
                "retornar um status tratável pela view."
            )

        self.assertIsNotNone(
            resultado,
            "BUG 5.4: `set_route_as_done` devolveu None mesmo no caminho de "
            "sucesso — o resto dos services já retorna valor explícito.",
        )


class CancelamentoDeInscricaoTests(TestCase):
    """REGRA DO TIME + RELATÓRIO 5.5 — cancelar inscrição destrói o aluno na métrica.

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

        self.assertEqual(
            restantes, 0,
            f"BUG 5.5: o cancelamento deixou {restantes} registro(s) antigo(s) "
            "no banco, porque `destruct_student` filtra por "
            "`day=timezone.localdate()`. Definir (relatório 5.5/9.2) se o "
            "cancelamento apaga só o pendente do dia ou o histórico todo.",
        )


class AssinaturaDosServicesTests(TestCase):
    """RELATÓRIO 5.3 — ``set_`` e ``get_`` trocam a ordem de ``line``/``route``."""

    def test_set_e_get_usam_a_mesma_ordem_de_argumentos(self):
        ordem_set = list(inspect.signature(service.set_last_stop_metrics).parameters)[:2]
        ordem_get = list(inspect.signature(service.get_last_stop_metrics).parameters)[:2]

        self.assertEqual(
            ordem_set, ordem_get,
            "BUG 5.3: `set_last_stop_metrics(line, route, ...)` e "
            f"`get_last_stop_metrics({', '.join(ordem_get)}, ...)` têm ordens "
            "diferentes. As duas primeiras posições são strings, então uma "
            "view chamando sem keyword troca linha por rota silenciosamente. "
            "Unificar a ordem (ou usar keyword-only).",
        )


class CodigoMortoTests(TestCase):
    """RELATÓRIO 5.7 — ``build_route_timeline_prediction`` é código morto.

    O corpo itera sobre ``route_stops = []`` (o model ``RouteStop``/``RotaParadas``
    não existe nesta branch) e, mesmo se existisse, mistura objeto FK
    (``rs.start_stop.name``) com o padrão "strings de ponta a ponta" adotado
    pelo resto do service.
    """

    def test_timeline_de_previsao_retorna_alguma_parada(self):
        resultado = service.build_route_timeline_prediction(LINHA, ROTA, current_order=1)

        self.assertTrue(
            resultado.get("timeline"),
            "BUG 5.7: a função promete a timeline de todas as paradas com ETA e "
            f"devolve {resultado!r} — o laço roda sobre `route_stops = []` "
            "hardcoded. Implementar de verdade (depende da app de rotas) ou "
            "remover/isolar com NotImplementedError.",
        )


class ModelDivergenteDaSpecTests(TestCase):
    """RELATÓRIO 5.6 — ``StopMetrics.distance`` sem precisão definida.

    O ``agent.md`` 2.1 manda ``max_digits=6, decimal_places=2``; sem isso o
    SQLite aceita qualquer coisa e o Postgres (já previsto no venv) cria um
    ``numeric`` sem precisão.
    """

    def test_distance_tem_precisao_definida(self):
        campo = StopMetrics._meta.get_field("distance")

        self.assertEqual(
            (campo.max_digits, campo.decimal_places), (6, 2),
            "BUG 5.6: `StopMetrics.distance` foi declarada como "
            "DecimalField() sem max_digits/decimal_places (valor atual: "
            f"{campo.max_digits}/{campo.decimal_places}). Usar os valores da "
            "spec: max_digits=6, decimal_places=2.",
        )


class AdminVazioTests(TestCase):
    """RELATÓRIO 5.8 — o admin funcional foi apagado (commit ``64af95a``).

    LIMITANTE: sem dashboard e sem admin, hoje não existe nenhuma tela em que
    o gestor veja uma métrica sequer.
    """

    def test_todos_os_models_de_metrica_estao_no_admin(self):
        modelos = (LastRouteDay, StopMetrics, StudentsUsingBus)
        faltando = [m.__name__ for m in modelos if m not in admin.site._registry]

        self.assertEqual(
            faltando, [],
            f"BUG 5.8: models sem admin registrada(o): {faltando}. Restaurar o "
            "`metrics/admin.py` apagado no commit 64af95a — visibilidade "
            "mínima do gestor enquanto o dashboard não existe.",
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


class IntegracaoPendenteTests(TestCase):
    """RELATÓRIO 4.6 — ninguém chama os services do metrics (VERMELHO esperado).

    LIMITANTE DO MVP: o projeto está em desenvolvimento e só tem as partes de
    **métricas** e **autenticação** — **ainda não existem as views de
    inscrição, presença, viagem, conclusão e cancelamento**, que são as que
    vão consumir estes services (o app metrics, por regra de arquitetura, não
    recebe requisições nem tem autorização própria). Estes testes ficam
    vermelhos até essas views aparecerem; eles não apontam bug do metrics,
    apontam o que falta no restante do MVP.
    """

    def test_urls_do_projeto_instanciam_a_app_metrics(self):
        padroes = [str(p.pattern) for p in get_resolver().url_patterns]

        self.assertIn(
            "metrics/", padroes,
            "LIMITANTE DO MVP (relatório 4.6): o include de metrics está "
            "comentado em core/urls.py e o arquivo metrics/urls.py nem existe. "
            "Hoje não há endpoint nenhum ligado às métricas.",
        )

    def test_views_consomem_os_services_de_metrica(self):
        esperados = {
            "register_student": "view de inscrição do aluno na rota",
            "destruct_student": "view de cancelamento da inscrição",
            "set_last_stop_metrics": "view/fluxo da viagem (chegada na parada)",
            "get_time_prediction": "view que devolve o horário previsto ao front",
            "set_route_as_done": "view/fluxo de conclusão da viagem",
            "start_trip_metric": "view/fluxo de partida do ônibus",
        }
        codigo = _codigo_das_outras_apps()
        faltantes = [f"{nome} ({uso})" for nome, uso in esperados.items() if nome not in codigo]

        self.assertEqual(
            faltantes, [],
            "LIMITANTE DO MVP (relatório 4.6): nenhum código fora de metrics "
            f"chama os services ainda. Faltando: {faltantes}. Enquanto as "
            "views do restante do MVP não existirem, nenhum dado entra e "
            "nenhum dado sai deste app.",
        )


class ChaveDeCacheTests(TestCase):
    """EXTRA (não constava no relatório) — a chave da partida tem espaços.

    Apareceu na primeira execução desta suíte: o Django emite
    ``CacheKeyWarning`` para a chave ``trip_start:Linha 1:Rota Centro:2026-09-25``,
    porque ``start_trip_metric`` monta a chave com os nomes literais de linha e
    rota. No LocMemCache (padrão atual, e ainda por cima por processo —
    relatório 5.1) isso é só um aviso; com memcached/redis em produção a chave
    é rejeitada, a partida da viagem se perde e o fluxo cai de volta no bug 4.3
    (ETA sempre 0).
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
            "EXTRA: a chave do cache não é portável para memcached/redis "
            f"(avisos: {avisos}). Sanitizar a chave em "
            "`start_trip_metric`/`set_last_stop_metrics` (ex.: sem espaços e "
            "sem `:` solto) e/ou configurar CACHES nos settings (relatório 5.1).",
        )






