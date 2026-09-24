"""
Testes automatizados do nucleo da app ``metrics`` (UniRota): services + cache.

Escopo desta primeira rodada - validar se o nucleo esta coeso:

    1. Calculos puros usados no KPI de ETA (``service.calculate_*`` e
       ``service.convert_km_to_m``).
    2. ``cache_handler.start_trip_cache``: o que e gravado para a partida do dia.
    3. Comportamentos do service que ja funcionam: guarda de horario com
       rollback da transacao e registro de aluno na rota.
    4. Coesao service <-> cache_handler <-> models: a classe
       ``FalhasDeCoesaoDoNucleoTests`` e o checklist desse contrato (mesmo
       padrao adotado em ``authentication/tests.py``). Situacao atual: o
       service foi alinhado para strings puros (sem ``.id``/objetos - o app
       de cadastro de rotas ainda nao existe), entao os problemas abaixo ja
       resolvidos viraram regressao; o que continua aberto:

       * [OK] a chave/payload do ``cache_handler`` agora e o que o ``service``
         procura (``trip_start:{line}:{route}:{data}`` + ``start_stop``);
       * [OK] ``line``/``route`` sao strings de ponta a ponta (CharField);
       * [OK] o ETA converte ``Decimal``/``float`` antes de dividir - sem
         TypeError e devolvendo inteiro de segundos;
       * [ABERTO - nao e foco agora] ``LastRouteDay.date`` e
         ``DateTimeField(auto_now_add=True)`` e o ``service`` filtra por
         ``timezone.now().date()`` - o cabecalho do dia nunca e reaproveitado,
         ou seja, o encadeamento de trechos (ordem >= 2) fica sem origem.

    5. Consistencia do tempo previsto (``get_time_prediction``): deve devolver
       SEGUNDOS inteiros de forma deterministica, escalar com a distancia,
       encolher quando o tramo anterior foi mais rapido, arredondar para cima
       (nunca subestimar a chegada) e caber em faixa plausivel de onibus na
       cidade (5 a 70 km/h).

Fora de escopo por enquanto: views, templates, urls e os edge cases combinados
(arredondamentos, distancia vinda de ``RotaParadas`` etc.).

Como rodar:

    python manage.py test metrics -v 2

O runner customizado ``SemChecagensDoProjetoRunner`` continua disponivel como
fallback (pula o ``check`` global e recria as tabelas da app no test DB caso
o ``include`` de ``metrics.urls`` volte a quebrar o check em ``core/urls.py``
ou a migration inicial suma): acrescente
``--testrunner=metrics.tests.SemChecagensDoProjetoRunner`` se precisar.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.runner import DiscoverRunner
from django.utils import timezone

from authentication.models import User

from . import cache_handler, service
from .models import LastRouteDay, StopMetrics, StudentsUsingBus

# Os testes criam usuario/validam senha; MD5 mantem a bateria rapida
# (mesma estrategia adotada em authentication/tests.py).
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LINHA = "Linha 1"
ROTA = "Rota Centro"


def _criar_tabelas_metrics():
    """Cria as tabelas ``metrics_*`` uma unica vez, apos o test DB ficar pronto.

    Se a app tiver pacote de migrations sem nenhuma migration (o que ja
    aconteceu aqui), o Django nao a sincroniza no setup e as tabelas nunca
    aparecem (dai os "no such table" nos primeiros testes de banco). Hoje
    ``metrics.0001_initial`` existe, entao este helper vira no-op (as tabelas
    ja vao existir). A constraint ``unique_*`` vem junto quando precisa criar:
    ``table_sql`` inclui ``Meta.constraints`` no proprio CREATE TABLE.
    """
    with connection.schema_editor(atomic=True) as editor:
        for model in (LastRouteDay, StopMetrics, StudentsUsingBus):
            if model._meta.db_table in connection.introspection.table_names():
                continue
            editor.create_model(model)


class SemChecagensDoProjetoRunner(DiscoverRunner):
    """DiscoverRunner que pula o ``check`` global e garante as tabelas da app.

    Fallback de seguranca: se o ``check`` global voltar a quebrar (ex.:
    ``core/urls.py`` voltar a importar ``metrics.urls``) ou a migration da app
    sumir, ``run_checks``/``setup_databases`` evitam derrubar a suite antes do
    primeiro teste (ver ``_criar_tabelas_metrics``).
    """

    def run_checks(self, databases):
        pass

    def setup_databases(self, **kwargs):
        aliases = super().setup_databases(**kwargs)
        _criar_tabelas_metrics()
        return aliases


class CacheLimpoTestCase(TestCase):
    """LocMemCache e por processo: limpa o cache antes de cada teste."""

    def setUp(self):
        super().setUp()
        cache.clear()


class IdentificadorFake:
    """Stub de Linha/Rota para o contrato que o ``service`` espera hoje.

    ``set_last_stop_metrics`` monta a chave do cache com ``.id`` e o CharField
    de ``LastRouteDay`` grava o nome usando ``str()``.
    """

    def __init__(self, id, nome):
        self.id = id
        self.nome = nome

    def __str__(self):
        return self.nome


def criar_aluno(email="aluno@unirotas.com"):
    """Cria um usuario direto pelo manager (bypassa os formularios)."""
    return User.objects.create_user(
        email=email, password="Senha@123", full_name="Aluno de Teste"
    )


def gravar_tramo(line, route, distance_km, duracao_segundos, order=1):
    """Grava um tramo ja concluido (cabecalho do dia + metrica) direto no banco.

    E o mesmo dado que ``set_last_stop_metrics`` escreveria durante a viagem;
    os testes de previsao usam o tramo anterior como base do calculo. Os
    horarios terminam no passado para a leitura bater com uma viagem real.
    """
    inicio = timezone.now() - timedelta(seconds=duracao_segundos + 300)
    cabecalho = LastRouteDay.objects.create(line=line, route=route)
    return StopMetrics.objects.create(
        last_route_day=cabecalho,
        start_stop="Terminal",
        end_stop="Praca Central",
        distance=distance_km,
        start_time=inicio,
        end_time=inicio + timedelta(seconds=duracao_segundos),
        order=order,
    )


# ---------------------------------------------------------------------------
# 1. Calculos puros usados pelo KPI de ETA
# ---------------------------------------------------------------------------
class CalculosDoETATests(TestCase):
    """Funcoes puras do service (delta, conversao e velocidade)."""

    def test_delta_time_em_segundos(self):
        inicio = timezone.now()
        fim = inicio + timedelta(minutes=35)

        self.assertEqual(service.calculate_delta_time(inicio, fim), 2100.0)

    def test_conversao_de_km_para_metros_e_velocidade_media(self):
        self.assertEqual(service.convert_km_to_m(1.5), 1500.0)

        # 1,5 km em 100 s -> 15 m/s
        self.assertAlmostEqual(
            service.calculate_meters_per_second(100, 1.5), 15.0, places=6
        )

    def test_velocidade_e_zero_quando_o_delta_nao_e_positivo(self):
        self.assertEqual(service.calculate_meters_per_second(0, 1.5), 0.0)
        self.assertEqual(service.calculate_meters_per_second(-30, 1.5), 0.0)

    def test_tempo_restante_arredonda_para_baixo_e_zera_sem_velocidade(self):
        # 255 m a 10 m/s -> 25,5 s -> floor = 25 s
        self.assertEqual(service.calculate_next_stop_time(10.0, 0.255), 25)
        self.assertEqual(service.calculate_next_stop_time(0, 0.255), 0)


# ---------------------------------------------------------------------------
# 2. cache_handler.start_trip_cache
# ---------------------------------------------------------------------------
class TripStartCacheTests(CacheLimpoTestCase):
    """O que fica gravado no cache quando a viagem do dia comeca."""

    def test_grava_parada_e_horario_da_partida(self):
        antes = timezone.now()
        cache_handler.start_trip_cache(LINHA, ROTA, "Terminal")
        depois = timezone.now()

        dados = cache.get(f"trip_start:{LINHA}:{ROTA}:{timezone.now().date()}")
        self.assertIsNotNone(dados)
        self.assertEqual(dados["start_stop"], "Terminal")
        self.assertTrue(antes <= dados["start_time"] <= depois)


# ---------------------------------------------------------------------------
# 3. Comportamentos do service que ja funcionam
# ---------------------------------------------------------------------------
class NucleoDoServiceTests(CacheLimpoTestCase):
    """Guarda de horario com rollback e registro de aluno na rota."""

    def setUp(self):
        super().setUp()
        self.linha = IdentificadorFake(1, LINHA)
        self.rota = IdentificadorFake(2, ROTA)

    def test_partida_no_futuro_levanta_value_error_e_desfaz_o_cabecalho(self):
        partida_no_futuro = {
            "start_stop": "Terminal",
            "start_time": timezone.now() + timedelta(minutes=10),
        }

        with patch("metrics.service.cache.get", return_value=partida_no_futuro):
            with self.assertRaises(ValueError):
                # assinatura atual: (line, route, parada, ordem, distance_km)
                service.set_last_stop_metrics(self.linha, self.rota, "Campus", 1, 1.5)

        # transaction.atomic precisa ter desfeito o cabecalho criado antes da validacao
        self.assertEqual(LastRouteDay.objects.count(), 0)
        self.assertEqual(StopMetrics.objects.count(), 0)

    def test_register_student_grava_o_uso_do_aluno_na_rota_do_dia(self):
        aluno = criar_aluno()

        service.register_student(aluno, ROTA)

        uso = StudentsUsingBus.objects.get()
        self.assertEqual(uso.user, aluno)
        self.assertEqual(uso.route, ROTA)
        self.assertEqual(uso.day, timezone.localdate())

    def test_register_student_repetido_e_barrado_pela_constraint(self):
        """Hoje quem protege contra retry/duplicidade e a constraint do banco.

        O agent.md pede que a escrita seja segura a retry do cliente; o service
        ainda nao e idempotente (deixa a IntegrityError subir). Este teste
        documenta o comportamento atual.
        """
        aluno = criar_aluno()
        service.register_student(aluno, ROTA)

        with self.assertRaises(IntegrityError), transaction.atomic():
            service.register_student(aluno, ROTA)

        self.assertEqual(StudentsUsingBus.objects.count(), 1)


# ---------------------------------------------------------------------------
# 4. Coesao do nucleo - checklist (1 ponto aberto: cabecalho do dia por data)
# ---------------------------------------------------------------------------
class FalhasDeCoesaoDoNucleoTests(CacheLimpoTestCase):
    """Checklist de coesao do nucleo (services + cache + models).

    O service foi alinhado para strings puros (sem ``.id``/objetos), entao 3
    dos 4 testes abaixo ja passam e funcionam como regressao do contrato; o
    unico vermelho e o reuso do cabecalho do dia por data - marcado no teste
    como nao e foco agora. Enquanto um teste falhar, ele serve de checklist
    da correcao - mesmo padrao adotado em ``authentication/tests.py``
    (``FalhasUrgentesTests``).
    """

    def setUp(self):
        super().setUp()
        self.linha = IdentificadorFake(1, LINHA)
        self.rota = IdentificadorFake(2, ROTA)

    def test_partida_gravada_pelo_cache_handler_deve_iniciar_o_primeiro_trecho(self):
        """Contrato da partida: o payload do handler inicia o primeiro trecho.

        Chave ``trip_start:{line}:{route}:{data}`` + chaves ``start_stop``/
        ``start_time`` gravadas pelo ``start_trip_cache`` devem ser lidas pelo
        ``set_last_stop_metrics``: o trecho nasce da parada de partida
        ("Terminal"), nao da parada atual ("Campus").
        """
        cache_handler.start_trip_cache("Linha101", "RotaIda", "Terminal")

        with patch("metrics.service.StopMetrics") as modelo:
            service.set_last_stop_metrics("Linha101", "RotaIda", "Campus", 1, 5)
            criado = modelo.objects.create.call_args.kwargs

        self.assertEqual(criado["start_stop"], "Terminal")

    def test_primeiro_trecho_deve_aceitar_line_e_route_como_no_modelo(self):
        """Contrato em strings: line/route sao CharField de ponta a ponta.

        Nenhum ponto do fluxo pode depender de ``.id``/objeto (o app de
        cadastro de rotas ainda nao existe) e o INSERT precisa chegar ao banco
        com ``distance`` (campo NOT NULL) preenchido.
        """
        cache_handler.start_trip_cache(LINHA, ROTA, "Campus")
        metrica = service.set_last_stop_metrics(LINHA, ROTA, "Campus", 1, 20)

        self.assertEqual(metrica.start_stop, "Campus")
        self.assertEqual(metrica.order, 1)

    # importante mas não foco agora
    def test_cabecalho_do_dia_deve_ser_reaproveitado_pelo_filtro_do_service(self):
        """RED - ``LastRouteDay.date`` e ``DateTimeField(auto_now_add=True)``, mas
        o service faz ``get_or_create(..., date=timezone.now().date())``. O
        filtro por ``date`` vira meia-noite e nunca casa com o datetime real
        gravado: cada chamada cria um cabecalho novo (o agent.md 3.1 pede um
        cabecalho unico por viagem/dia).

        Efeito colateral: o cabecalho novo nao tem a metrica da ordem anterior,
        entao ``get_last_stop_metrics`` devolve None e o encadeamento de
        trechos (ordem >= 2) morre com AttributeError.
        """
        cabecalho = LastRouteDay.objects.create(line=LINHA, route=ROTA)

        reaproveitado, criado = LastRouteDay.objects.get_or_create(
            line=LINHA, route=ROTA, date=timezone.now().date()
        )

        self.assertFalse(criado)
        self.assertEqual(reaproveitado.pk, cabecalho.pk)

    def test_eta_com_distancia_lida_do_banco_nao_deve_estourar_tipo(self):
        """Regressao de tipos: ``distance`` volta do banco como Decimal e o ETA
        precisa converte-lo antes de dividir - sem TypeError e devolvendo
        inteiro de segundos.
        """
        agora = timezone.now()
        cabecalho = LastRouteDay.objects.create(line=LINHA, route=ROTA)
        criada = StopMetrics.objects.create(
            last_route_day=cabecalho,
            start_stop="Terminal",
            end_stop="Praca Central",
            distance=2.0,
            start_time=agora - timedelta(minutes=40),
            end_time=agora - timedelta(minutes=5),
            order=1,
        )
        # releitura: e assim que o ETA enxerga a metrica (Decimal, nao float)
        metrica = StopMetrics.objects.get(pk=criada.pk)

        with patch("metrics.service.get_last_stop_metrics", return_value=metrica):
            resultado = service.get_time_prediction(LINHA, ROTA, 2, 1.0)

        self.assertIsInstance(resultado, int)


# ---------------------------------------------------------------------------
# 5. Consistencia do tempo previsto (ETA) - o tempo devolvido faz sentido?
# ---------------------------------------------------------------------------
class ConsistenciaDoTempoPrevistoTests(TestCase):
    """``get_time_prediction`` precisa devolver segundos consistentes.

    Cenario base (gravado no ``setUp``): o tramo anterior percorreu 3,6 km em
    12 min, ou seja 5 m/s = 18 km/h - ritmo plausivel de onibus na cidade.
    Nesse ritmo a previsao e exata e verificavel a mao: 1 km = 200 s,
    2 km = 400 s (~6,7 min) e 4 km = 800 s.
    """

    def setUp(self):
        super().setUp()
        self.tramo_anterior = gravar_tramo(LINHA, ROTA, 3.6, 720)

    def test_retorna_inteiro_de_segundos_com_o_valor_esperado(self):
        previsao = service.get_time_prediction(LINHA, ROTA, 2, 2.0)

        self.assertIsInstance(previsao, int)  # segundos inteiros, nao float
        self.assertEqual(previsao, 400)       # 2 km a 5 m/s = 400 s

    def test_repetir_a_mesma_chamada_retorna_o_mesmo_tempo(self):
        chamadas = [service.get_time_prediction(LINHA, ROTA, 2, 2.0) for _ in range(3)]

        self.assertTrue(all(isinstance(s, int) for s in chamadas))
        self.assertEqual(len(set(chamadas)), 1)  # mesmo dado de entrada, mesma saida

    def test_tempo_cresce_proporcionalmente_com_a_distancia(self):
        um_km = service.get_time_prediction(LINHA, ROTA, 2, 1.0)
        dois_km = service.get_time_prediction(LINHA, ROTA, 2, 2.0)
        quatro_km = service.get_time_prediction(LINHA, ROTA, 2, 4.0)

        self.assertEqual((um_km, dois_km, quatro_km), (200, 400, 800))
        self.assertEqual(quatro_km, 2 * dois_km)  # dobro da distancia, dobro do tempo

    def test_tempo_menor_quando_o_tramo_anterior_foi_mais_rapido(self):
        # mesmo tramo de 3,6 km, mas feito em 6 min = 10 m/s (dobro da velocidade)
        gravar_tramo("Linha 102", ROTA, 3.6, 360)

        mais_lento = service.get_time_prediction(LINHA, ROTA, 2, 2.0)
        mais_rapido = service.get_time_prediction("Linha 102", ROTA, 2, 2.0)

        self.assertEqual((mais_rapido, mais_lento), (200, 400))
        self.assertLess(mais_rapido, mais_lento)

    def test_arredondamento_para_cima_nunca_subestima_a_chegada(self):
        """ETA arredonda para cima (ceil) e a contagem para o proximo ponto,
        para baixo (floor) - com 125 m a 6 m/s (20,83 s) as duas direcoes
        ficam claras.
        """
        gravar_tramo("Linha 103", ROTA, 3.6, 600)  # 3,6 km em 10 min = 6 m/s

        previsao = service.get_time_prediction("Linha 103", ROTA, 2, 0.125)
        contagem = service.calculate_next_stop_time(6.0, 0.125)

        self.assertEqual(previsao, 21)  # ceil(20,83 s): nao subestima o tempo
        self.assertEqual(contagem, 20)  # floor(20,83 s)
        self.assertLess(contagem, previsao)

    def test_tempo_faz_sentido_para_um_onibus_na_cidade(self):
        """Sanidade: velocidade em faixa plausivel e previsao em faixa razoavel."""
        delta = service.calculate_delta_time(
            self.tramo_anterior.start_time, self.tramo_anterior.end_time
        )
        velocidade = service.calculate_meters_per_second(
            delta, self.tramo_anterior.distance
        )
        km_por_h = float(velocidade) * 3.6
        previsao = service.get_time_prediction(LINHA, ROTA, 2, 2.0)

        self.assertEqual(delta, 720.0)           # o tramo realmente durou 12 min
        self.assertTrue(5 <= km_por_h <= 70)     # 18 km/h: plausivel na cidade
        self.assertTrue(60 <= previsao <= 1800)  # 2 km nesse ritmo: 1 a 30 min


# Fim dos testes de coesao e consistencia do nucleo da app metrics.
# O unico ponto ainda aberto e o reuso do cabecalho do dia por data (marcado
# no teste como nao e foco agora); quando ele passar, remova a marcacao e
# registre a correcao no commit.


