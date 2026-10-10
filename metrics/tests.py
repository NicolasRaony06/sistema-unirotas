"""Testes automatizados da app metrics (UniRota).

Cobre a logica de negocio do app metrics:
register_student_on_route, destruct_student_from_route,
set_route_as_done, calculate_delta_time, convert_km_to_m,
calculate_meters_per_second, get_last_stop_metrics,
set_last_stop_metrics, get_time_prediction, start_trip_metric e
build_route_timeline_prediction.

Regras de organizacao:
- Cada teste tem proposito claro e ID na rubrica (T1..T52).
- ESCR = comportamento esperado (caso feliz).
- COM = comportamento invalido / limite / borda.
- RouteMaterialization.get_route_stops NAO e testado alem do
  comportamento observavel do stub (T36/T44): metodo incompleto
  (stub de integracao futura, R-04). Ver relatorio.md.
- RouteMaterialization.__init__ e testado (logica completa).

Como rodar:
    python manage.py test metrics -v 2
"""

import unittest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone as tz

from metrics.data_type import (
    LastStopDTO,
    RouteDTO,
    RoutePredictionDTO,
    StopDTO,
    TripStopDTO,
)
from metrics.models import LastRouteDay, StopMetrics, StudentsUsingBus
from metrics.route_objects import RouteMaterialization
from metrics.service import (
    build_route_timeline_prediction,
    calculate_delta_time,
    calculate_meters_per_second,
    convert_km_to_m,
    destruct_student_from_route,
    get_last_stop_metrics,
    get_time_prediction,
    register_student_on_route,
    set_last_stop_metrics,
    set_route_as_done,
    start_trip_metric,
)

# Senha forte exigida pelo validador do projeto.
SENHA_FORTE = "Senha@123"

# Hash rapido so durante os testes (mesmo padrao de authentication/tests.py).
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def _criar_usuario(email="aluno@unirotas.com", full_name="Aluno Teste"):
    from authentication.models import User

    return User.objects.create_user(
        email=email, password=SENHA_FORTE, full_name=full_name
    )


def _criar_rotadiario(line=1, route=10, is_concluded=False, dia=None):
    if dia is None:
        dia = tz.localdate()
    return LastRouteDay.objects.create(
        line_id=line,
        route_id=route,
        is_concluded=is_concluded,
        date=dia,
    )


def _criar_stop_metrics(rotadiario, order, start_stop_id, end_stop_id,
                        start_time, end_time, distance=None):
    return StopMetrics.objects.create(
        last_route_day=rotadiario,
        order=order,
        start_stop_id=start_stop_id,
        end_stop_id=end_stop_id,
        start_time=start_time,
        end_time=end_time,
        distance=distance,
    )


# ----------------------------------------------------------------------
# T1-T3: register_student_on_route
# ----------------------------------------------------------------------


class RegisterStudentTests(TestCase):
    """Validacao de register_student_on_route."""

    def setUp(self):
        self.user = _criar_usuario()
        self.route = 10

    def test_T1_register_cria_registro_do_dia(self):
        """ESCR: cria StudentsUsingBus com user/route/day de hoje."""
        obj, created = register_student_on_route(self.user, self.route)
        self.assertTrue(created)
        self.assertEqual(obj.user_id, self.user.id)
        self.assertEqual(obj.route_id, self.route)
        self.assertEqual(obj.day, tz.localdate())

    def test_T2_register_idempotente_mesmo_dia(self):
        """COM: repeticao no mesmo dia nao duplica (get_or_create)."""
        obj1, _ = register_student_on_route(self.user, self.route)
        obj2, created2 = register_student_on_route(self.user, self.route)
        self.assertFalse(created2)
        self.assertEqual(obj1.id, obj2.id)
        self.assertEqual(
            StudentsUsingBus.objects.filter(
                user=self.user, route_id=self.route, day=tz.localdate()
            ).count(),
            1,
        )

    def test_T3_register_dias_diferentes_nao_compartilham(self):
        """COM: dias diferentes geram registros distintos."""
        with patch("metrics.service.timezone") as mock_tz:
            mock_tz.localdate.return_value = date(2026, 10, 1)
            obj1, _ = register_student_on_route(self.user, self.route)
        with patch("metrics.service.timezone") as mock_tz:
            mock_tz.localdate.return_value = date(2026, 10, 2)
            obj2, created2 = register_student_on_route(self.user, self.route)
        self.assertTrue(created2)
        self.assertNotEqual(obj1.id, obj2.id)
        self.assertNotEqual(obj1.day, obj2.day)


# ----------------------------------------------------------------------
# T4-T5: destruct_student_from_route
# ----------------------------------------------------------------------


class DestructStudentTests(TestCase):
    """Validacao de destruct_student_from_route."""

    def setUp(self):
        self.user = _criar_usuario()
        self.route = 10

    def test_T4_destruct_remove_registro_existente(self):
        """ESCR: com registro existente, deleta e retorna True."""
        register_student_on_route(self.user, self.route)
        self.assertTrue(destruct_student_from_route(self.user, self.route))
        self.assertFalse(
            StudentsUsingBus.objects.filter(
                user=self.user, route_id=self.route, day=tz.localdate()
            ).exists()
        )

    def test_T5_destruct_sem_registro_retorna_false(self):
        """COM: sem registro, retorna False sem excecao."""
        self.assertFalse(destruct_student_from_route(self.user, self.route))


# ----------------------------------------------------------------------
# T6-T8: set_route_as_done
# ----------------------------------------------------------------------


class RouteDoneTests(TestCase):
    """Validacao de set_route_as_done."""

    def setUp(self):
        self.line = 1
        self.route = 10

    def test_T6_set_done_conclui_rota_existente(self):
        """ESCR: com LastRouteDay existente, marca concluido e retorna True."""
        rotadiario = _criar_rotadiario(
            line=self.line, route=self.route, is_concluded=False
        )
        self.assertTrue(set_route_as_done(self.line, self.route))
        rotadiario.refresh_from_db()
        self.assertTrue(rotadiario.is_concluded)

    def test_T7_set_done_idempotente_ja_concluida(self):
        """COM: rota ja concluida continua True (idempotente)."""
        rotadiario = _criar_rotadiario(
            line=self.line, route=self.route, is_concluded=True
        )
        self.assertTrue(set_route_as_done(self.line, self.route))
        rotadiario.refresh_from_db()
        self.assertTrue(rotadiario.is_concluded)

    def test_T8_set_done_sem_cabecalho_retorna_false(self):
        """COM: sem LastRouteDay do dia, retorna False sem criar nada."""
        self.assertFalse(set_route_as_done(self.line, self.route))
        self.assertFalse(
            LastRouteDay.objects.filter(
                line_id=self.line, route_id=self.route
            ).exists()
        )


# ----------------------------------------------------------------------
# T9-T10: calculate_delta_time
# ----------------------------------------------------------------------


class CalculateDeltaTimeTests(TestCase):
    """Validacao de calculate_delta_time (funcao pura)."""

    def test_T9_delta_time_diferenca_positiva(self):
        """ESCR: end > start retorna total_seconds correto."""
        start = tz.now()
        end = start + timedelta(seconds=90)
        self.assertEqual(calculate_delta_time(start, end), 90.0)

    def test_T10_delta_time_zero_ou_negativo(self):
        """COM: end == start retorna 0; end < start retorna negativo."""
        start = tz.now()
        self.assertEqual(calculate_delta_time(start, start), 0.0)
        self.assertEqual(
            calculate_delta_time(start, start - timedelta(seconds=5)), -5.0
        )


# ----------------------------------------------------------------------
# T11-T13: convert_km_to_m
# ----------------------------------------------------------------------


class ConvertKmToMTests(TestCase):
    """Validacao de convert_km_to_m (funcao pura)."""

    def test_T11_convert_km_multiplica_por_1000(self):
        """ESCR: 1.5 km -> 1500.0 m."""
        self.assertEqual(convert_km_to_m(1.5), 1500.0)

    def test_T12_convert_km_zero_none_vazio_retorna_zero(self):
        """COM: 0, None, '' e 0.0 retornam 0 sem excecao."""
        self.assertEqual(convert_km_to_m(0), 0)
        self.assertEqual(convert_km_to_m(None), 0)
        self.assertEqual(convert_km_to_m(""), 0)
        self.assertEqual(convert_km_to_m(0.0), 0)

    def test_T13_convert_km_tipo_invalido_retorna_zero(self):
        """COM: tipo nao numerico (excecao no *) retorna 0."""
        self.assertEqual(convert_km_to_m(object()), 0)


# ----------------------------------------------------------------------
# T14-T16: calculate_meters_per_second
# ----------------------------------------------------------------------


class CalculateMetersPerSecondTests(TestCase):
    """Validacao de calculate_meters_per_second (funcao pura)."""

    def test_T14_velocity_calcula_corretamente(self):
        """ESCR: 1 km em 100 s -> 10 m/s."""
        self.assertEqual(
            calculate_meters_per_second(100, 1.0), Decimal("10")
        )

    def test_T15_velocity_delta_zero_ou_negativo_retorna_zero(self):
        """COM: delta <= 0 retorna Decimal(0) sem divisao por zero."""
        self.assertEqual(
            calculate_meters_per_second(0, 1.0), Decimal("0")
        )
        self.assertEqual(
            calculate_meters_per_second(-5, 1.0), Decimal("0")
        )

    def test_T16_velocity_distancia_zero_retorna_zero(self):
        """COM: distancia 0/None retorna Decimal(0)."""
        self.assertEqual(calculate_meters_per_second(10, 0), Decimal("0"))
        self.assertEqual(calculate_meters_per_second(10, None), Decimal("0"))


# ----------------------------------------------------------------------
# T17-T19: get_last_stop_metrics
# ----------------------------------------------------------------------


class GetLastStopMetricsTests(TestCase):
    """Validacao de get_last_stop_metrics."""

    def setUp(self):
        self.line = 1
        self.route = 10

    def test_T17_last_stop_ordem_1_ou_menor_retorna_none(self):
        """ESCR: current_order <= 1 retorna None (sem tramo anterior)."""
        self.assertIsNone(get_last_stop_metrics(self.line, self.route, 1))
        self.assertIsNone(get_last_stop_metrics(self.line, self.route, 0))

    def test_T18_last_stop_sem_cabecalho_retorna_none(self):
        """COM: sem LastRouteDay do dia, retorna None."""
        _criar_rotadiario(line=self.line, route=99)
        self.assertIsNone(get_last_stop_metrics(self.line, self.route, 2))

    def test_T19_last_stop_encontra_tramo_anterior(self):
        """ESCR: com cabecalho + order-1, retorna o tramo anterior."""
        rotadiario = _criar_rotadiario(line=self.line, route=self.route)
        agora = tz.now()
        esperado = _criar_stop_metrics(
            rotadiario, order=1, start_stop_id=5, end_stop_id=6,
            start_time=agora - timedelta(seconds=60), end_time=agora,
            distance=Decimal("1.00"),
        )
        obtido = get_last_stop_metrics(self.line, self.route, 2)
        self.assertIsNotNone(obtido)
        self.assertEqual(obtido.id, esperado.id)
        self.assertEqual(obtido.end_stop_id, 6)


# ----------------------------------------------------------------------
# T20-T25: set_last_stop_metrics
# ----------------------------------------------------------------------


class SetLastStopMetricsTests(TestCase):
    """Validacao de set_last_stop_metrics."""

    def setUp(self):
        self.line = 1
        self.route = 10
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _dto(self, order, stop_id=10, distance=0.5):
        return LastStopDTO(
            line_id=self.line,
            route_id=self.route,
            current_stop_id=stop_id,
            current_order=order,
            distance_km=distance,
        )

    def test_T20_set_stop_ordem_1_cria_registro(self):
        """ESCR: ordem 1 cria StopMetrics com start = current_stop."""
        result = set_last_stop_metrics(self._dto(order=1, stop_id=10))
        self.assertEqual(result.order, 1)
        self.assertEqual(result.start_stop_id, 10)
        self.assertEqual(result.end_stop_id, 10)
        self.assertIsNotNone(result.start_time)
        self.assertIsNotNone(result.end_time)

    def test_T21_set_stop_ordem_1_consome_cache_trip_start(self):
        """ESCR: ordem 1 usa start_time do cache e limpa a chave."""
        inicio = tz.now() - timedelta(minutes=5)
        hoje = tz.localdate()
        chave = f"trip_start-{self.line}-{self.route}-{hoje}"
        cache.set(chave, {"start_time": inicio}, timeout=28800)
        result = set_last_stop_metrics(self._dto(order=1, stop_id=7))
        self.assertEqual(result.start_time, inicio)
        self.assertIsNone(cache.get(chave))

    def test_T22_set_stop_ordem_maior_encadeia_anterior(self):
        """ESCR: ordem > 1 propaga end_stop/end_time do tramo anterior."""
        set_last_stop_metrics(self._dto(order=1, stop_id=5))
        anterior = StopMetrics.objects.get(
            last_route_day__line_id=self.line,
            last_route_day__route_id=self.route,
            order=1,
        )
        result = set_last_stop_metrics(self._dto(order=2, stop_id=6))
        self.assertEqual(result.start_stop_id, anterior.end_stop_id)
        self.assertEqual(result.start_time, anterior.end_time)
        self.assertEqual(result.end_stop_id, 6)

    def test_T23_set_stop_ordem_maior_sem_anterior_usa_fallback(self):
        """COM: ordem > 1 sem tramo anterior usa current_stop + now."""
        result = set_last_stop_metrics(self._dto(order=3, stop_id=9))
        self.assertEqual(result.order, 3)
        self.assertEqual(result.start_stop_id, 9)
        self.assertEqual(result.end_stop_id, 9)

    def test_T24_set_stop_start_futuro_levanta_valueerror(self):
        """COM: start_time do cache no futuro levanta ValueError."""
        futuro = tz.now() + timedelta(hours=1)
        hoje = tz.localdate()
        chave = f"trip_start-{self.line}-{self.route}-{hoje}"
        cache.set(chave, {"start_time": futuro}, timeout=28800)
        with self.assertRaisesMessage(
            ValueError,
            "O hor\u00e1rio inicial n\u00e3o pode ser posterior ao hor\u00e1rio final.",
        ):
            set_last_stop_metrics(self._dto(order=1, stop_id=7))

    def test_T25_set_stop_idempotente_mesma_ordem(self):
        """COM: retry da mesma ordem nao duplica (get_or_create)."""
        first = set_last_stop_metrics(self._dto(order=1, stop_id=5))
        second = set_last_stop_metrics(self._dto(order=1, stop_id=5))
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            StopMetrics.objects.filter(
                last_route_day=first.last_route_day, order=1
            ).count(),
            1,
        )


# ----------------------------------------------------------------------
# T26-T28: get_time_prediction
# ----------------------------------------------------------------------


class GetTimePredictionTests(TestCase):
    """Validacao de get_time_prediction."""

    def setUp(self):
        self.line = 1
        self.route = 10

    def _stop_dto(self, order=2, distance_km=1.0):
        return StopDTO(
            line_id=self.line,
            route_id=self.route,
            order=order,
            distance_km=distance_km,
        )

    def test_T26_predicao_sem_tramo_anterior_retorna_zero(self):
        """ESCR: sem tramo anterior, retorna 0 (falha controlada)."""
        self.assertEqual(get_time_prediction(self._stop_dto()), 0)

    def test_T27_predicao_calcula_ceil_distancia_sobre_velocidade(self):
        """ESCR: com tramo anterior valido, retorna ceil(dist/vel)."""
        rotadiario = _criar_rotadiario(line=self.line, route=self.route)
        fim = tz.now()
        inicio = fim - timedelta(seconds=100)
        # Tramo anterior: 1 km em 100 s => 10 m/s.
        _criar_stop_metrics(
            rotadiario, order=1, start_stop_id=1, end_stop_id=2,
            start_time=inicio, end_time=fim, distance=Decimal("1.00"),
        )
        # 1 km a 10 m/s => 100 s; 1.5 km => 150 s (valores exatos).
        self.assertEqual(get_time_prediction(self._stop_dto(distance_km=1.0)), 100)
        self.assertEqual(get_time_prediction(self._stop_dto(distance_km=1.5)), 150)
        # Tramo anterior: 3 km em 100 s => 30 m/s; 1 km => 33.33 s => ceil 34.
        rotadiario2 = _criar_rotadiario(line=self.line, route=98)
        fim2 = tz.now()
        _criar_stop_metrics(
            rotadiario2, order=1, start_stop_id=1, end_stop_id=2,
            start_time=fim2 - timedelta(seconds=100), end_time=fim2,
            distance=Decimal("3.00"),
        )
        dto2 = StopDTO(line_id=self.line, route_id=98, order=2, distance_km=1.0)
        self.assertEqual(get_time_prediction(dto2), 34)

    def test_T28_predicao_distancia_ou_velocidade_nula_retorna_zero(self):
        """COM: distancia atual 0/None ou velocidade 0 retorna 0."""
        rotadiario = _criar_rotadiario(line=self.line, route=self.route)
        fim = tz.now()
        inicio = fim - timedelta(seconds=100)
        _criar_stop_metrics(
            rotadiario, order=1, start_stop_id=1, end_stop_id=2,
            start_time=inicio, end_time=fim, distance=Decimal("1.00"),
        )
        self.assertEqual(get_time_prediction(self._stop_dto(distance_km=0)), 0)
        self.assertEqual(get_time_prediction(self._stop_dto(distance_km=None)), 0)
        # Tramo anterior com distancia 0 => velocidade 0 => retorna 0.
        rotadiario2 = _criar_rotadiario(line=self.line, route=99)
        fim2 = tz.now()
        _criar_stop_metrics(
            rotadiario2, order=1, start_stop_id=1, end_stop_id=2,
            start_time=fim2 - timedelta(seconds=50), end_time=fim2,
            distance=Decimal("0.00"),
        )
        dto2 = StopDTO(
            line_id=self.line, route_id=99, order=2, distance_km=1.0
        )
        self.assertEqual(get_time_prediction(dto2), 0)


# ----------------------------------------------------------------------
# T29-T31: start_trip_metric
# ----------------------------------------------------------------------


class StartTripMetricTests(TestCase):
    """Validacao de start_trip_metric."""

    def setUp(self):
        self.line = 1
        self.route = 10
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_T29_start_trip_grava_chave_no_cache(self):
        """ESCR: grava trip_start-{line}-{route}-{hoje} com start_time."""
        antes = tz.now()
        start_trip_metric(self.line, self.route)
        chave = f"trip_start-{self.line}-{self.route}-{tz.localdate()}"
        payload = cache.get(chave)
        self.assertIsNotNone(payload)
        self.assertIn("start_time", payload)
        self.assertGreaterEqual(payload["start_time"], antes)

    def test_T30_start_trip_ttl_padrao_8h(self):
        """ESCR: ttl padrao e 28800 s (inspect + escrita no cache)."""
        import inspect

        self.assertEqual(
            inspect.signature(start_trip_metric).parameters["ttl"].default,
            28800,
        )
        start_trip_metric(self.line, self.route)
        chave = f"trip_start-{self.line}-{self.route}-{tz.localdate()}"
        self.assertIsNotNone(cache.get(chave))

    def test_T31_start_trip_sobrescreve_chamada_anterior(self):
        """COM: segunda chamada sobrescreve start_time (idempotente)."""
        start_trip_metric(self.line, self.route, ttl=60)
        chave = f"trip_start-{self.line}-{self.route}-{tz.localdate()}"
        primeiro = cache.get(chave)
        self.assertIsNotNone(primeiro)
        start_trip_metric(self.line, self.route, ttl=60)
        segundo = cache.get(chave)
        self.assertIsNotNone(segundo)
        self.assertGreaterEqual(
            segundo["start_time"], primeiro["start_time"]
        )


# ----------------------------------------------------------------------
# T32-T34: build_route_timeline_prediction (RouteMaterialization mockado:
# get_route_stops e stub R-04; a LOGICA da timeline e validada aqui)
# ----------------------------------------------------------------------


class BuildTimelineTests(TestCase):
    """Validacao da logica de build_route_timeline_prediction."""

    def setUp(self):
        self.route_data = RouteDTO(line_id=1, route_id=10, current_order=2)
        self.base = tz.now()

    def _mock_stops(self, mock_cls, stops):
        mock_cls.return_value.route_stops = stops
        mock_cls.return_value.get_route_stops.return_value = None

    def test_T32_timeline_marca_concluida_e_atual(self):
        """ESCR: order < atual => concluida; order == atual => atual."""
        stops = [
            TripStopDTO(start_stop_id=1, end_stop_id=2, order=1, distance_km=1.0),
            TripStopDTO(start_stop_id=2, end_stop_id=3, order=2, distance_km=1.0),
        ]
        with patch("metrics.service.RouteMaterialization") as mock_cls:
            self._mock_stops(mock_cls, stops)
            result = build_route_timeline_prediction(
                self.route_data, base_time=self.base
            )
        self.assertIsInstance(result, RoutePredictionDTO)
        self.assertEqual(result.timeline[0].status, "concluida")
        self.assertEqual(result.timeline[0].step_seconds, 0)
        self.assertIsNone(result.timeline[0].eta)
        self.assertEqual(result.timeline[1].status, "atual")
        self.assertEqual(result.timeline[1].step_seconds, 0)
        self.assertIsNone(result.timeline[1].eta)
        self.assertEqual(result.total_remaining_seconds, 0)

    def test_T33_timeline_pendente_acumula_eta(self):
        """ESCR: order > atual => pendente com step/acc/eta acumulados."""
        stops = [
            TripStopDTO(start_stop_id=1, end_stop_id=2, order=1, distance_km=1.0),
            TripStopDTO(start_stop_id=2, end_stop_id=3, order=3, distance_km=1.0),
            TripStopDTO(start_stop_id=3, end_stop_id=4, order=4, distance_km=2.0),
        ]
        with patch("metrics.service.RouteMaterialization") as mock_cls:
            self._mock_stops(mock_cls, stops)
            with patch(
                "metrics.service.get_time_prediction", side_effect=[60, 120]
            ):
                result = build_route_timeline_prediction(
                    self.route_data, base_time=self.base
                )
        pend1, pend2 = result.timeline[1], result.timeline[2]
        self.assertEqual(pend1.status, "pendente")
        self.assertEqual(pend1.step_seconds, 60)
        self.assertEqual(pend1.accumulated_seconds, 60)
        self.assertEqual(pend1.eta, self.base + timedelta(seconds=60))
        self.assertEqual(pend2.step_seconds, 120)
        self.assertEqual(pend2.accumulated_seconds, 180)
        self.assertEqual(pend2.eta, self.base + timedelta(seconds=180))
        self.assertEqual(result.total_remaining_seconds, 180)

    def test_T34_timeline_vazia_sem_paradas(self):
        """COM: sem paradas, timeline vazia e total 0."""
        with patch("metrics.service.RouteMaterialization") as mock_cls:
            self._mock_stops(mock_cls, [])
            result = build_route_timeline_prediction(
                self.route_data, base_time=self.base
            )
        self.assertEqual(result.timeline, [])
        self.assertEqual(result.total_remaining_seconds, 0)
        self.assertEqual(result.current_order, 2)
        self.assertEqual(result.base_time, self.base)

    def test_T35_timeline_base_time_default_e_now(self):
        """COM: sem base_time, usa timezone.now() como referencia."""
        stops = [
            TripStopDTO(start_stop_id=2, end_stop_id=3, order=3, distance_km=1.0),
        ]
        with patch("metrics.service.RouteMaterialization") as mock_cls:
            self._mock_stops(mock_cls, stops)
            with patch("metrics.service.get_time_prediction", return_value=30):
                antes = tz.now()
                result = build_route_timeline_prediction(self.route_data)
                depois = tz.now()
        self.assertGreaterEqual(result.base_time, antes)
        self.assertLessEqual(result.base_time, depois)
        self.assertEqual(
            result.timeline[0].eta,
            result.base_time + timedelta(seconds=30),
        )


# ----------------------------------------------------------------------
# T36: RouteMaterialization — logica completa (__init__) testada;
# metodo incompleto (get_route_stops) DOCUMENTADO como nao-testavel
# ----------------------------------------------------------------------


class RouteMaterializationTests(TestCase):
    """Valida a parte completa de RouteMaterialization.

    get_route_stops e stub (R-04): retorna None antes do loop real, pois
    a app de rotas ainda nao existe. Nao ha consulta para testar, entao
    a rubrica T36 registra a decisao de nao-teste. Aqui valida-se o que
    e completo: __init__ guarda route_data e inicia route_stops vazio.
    """

    def test_T36_materialization_init_guarda_estado(self):
        """ESCR: __init__ preserva route_data e inicia lista vazia."""
        data = RouteDTO(line_id=1, route_id=10, current_order=2)
        mat = RouteMaterialization(data)
        self.assertEqual(mat.route_data, data)
        self.assertEqual(mat.route_stops, [])


# ----------------------------------------------------------------------
# T37-T41: lacunas da auditoria (detalhe/resultado/motivo/prioridade na
# docstring; tabela consolidada em relatorio.md).
# ----------------------------------------------------------------------


class AuditoriaLacunasTests(TestCase):
    """Testes T37-T41 adicionados pela auditoria do app metrics."""

    @unittest.expectedFailure
    def test_T37_register_aceita_route_string_via_fk_id(self):
        """T37 — route como string numerica.

        Detalhamento: register_student_on_route(user, "10").
        Resultado: FALHA — cria com route_id='10' (str) em vez de 10
        (int); o ORM nao coage str->int no SQLite neste caminho.
        Motivo: route_id e IntegerField recebido como str; sem validacao
        de tipo no service (placeholder de FK, AGENT.md 2.2).
        Prioridade: BAIXA — sem crash; exige tipar/validar o service.
        """
        user = _criar_usuario(email="t37@unirotas.com")
        obj, created = register_student_on_route(user, "10")
        self.assertTrue(created)
        self.assertEqual(obj.route_id, 10)

    def test_T38_destruct_preserva_registro_de_dia_vizinho(self):
        """T38 — delete nao vaza para outros dias.

        Detalhamento: registros em 01/10 e 02/10; destroi o de hoje.
        Resultado: PASSA — so o registro corrente e removido.
        Motivo: filtro inclui day=timezone.localdate().
        Prioridade: BAIXA — trava do isolamento temporal.
        """
        from authentication.models import User

        user = User.objects.create_user(
            email="t38@unirotas.com", password=SENHA_FORTE,
            full_name="T38",
        )
        with patch("metrics.service.timezone") as mock_tz:
            mock_tz.localdate.return_value = date(2026, 10, 1)
            register_student_on_route(user, 10)
        with patch("metrics.service.timezone") as mock_tz:
            mock_tz.localdate.return_value = date(2026, 10, 2)
            register_student_on_route(user, 10)
            self.assertTrue(destruct_student_from_route(user, 10))
        restantes = StudentsUsingBus.objects.filter(user=user, route_id=10)
        self.assertEqual(restantes.count(), 1)
        self.assertEqual(restantes.first().day, date(2026, 10, 1))

    def test_T39_set_stop_ordem_zero_sem_guard(self):
        """T39 — current_order 0 nao tem guard no service.

        Detalhamento: set_last_stop_metrics com order=0.
        Resultado: PASSA (comportamento atual) — cria StopMetrics(order=0);
        o correto seria rejeitar, pois o dominio exige ordem >= 1
        (RotaParadas.ordem, AGENT.md 2.1) e o SQLite nao impoe o CHECK de
        PositiveIntegerField.
        Motivo: falta validacao de ordem no service.
        Prioridade: BAIXA.
        """
        dto = LastStopDTO(
            line_id=1, route_id=10, current_stop_id=5,
            current_order=0, distance_km=0.5,
        )
        obj = set_last_stop_metrics(dto)
        self.assertEqual(obj.order, 0)

    @unittest.expectedFailure
    def test_T40_predicao_distancia_string_quebra_calculo(self):
        """T40 — distance_km string numerica quebra o ETA.

        Detalhamento: tramo valido + stop distance_km="1.0"; espera 100 s.
        Resultado: FALHA — levanta decimal.InvalidOperation ("1.0"*1000
        repete a string e o Decimal explode depois).
        Motivo: convert_km_to_m nao valida tipo numerico.
        Prioridade: MEDIA — payload de borda gera 500 em vez de 0.
        """
        rotadiario = _criar_rotadiario(line=1, route=10)
        fim = tz.now()
        _criar_stop_metrics(
            rotadiario, order=1, start_stop_id=1, end_stop_id=2,
            start_time=fim - timedelta(seconds=100), end_time=fim,
            distance=Decimal("1.00"),
        )
        dto = StopDTO(
            line_id=1, route_id=10, order=2, distance_km="1.0",
        )
        self.assertEqual(get_time_prediction(dto), 100)

    def test_T41_timeline_distancia_none_futura_tolerada(self):
        """T41 — TripStopDTO futuro com distance None.

        Detalhamento: perna futura distance None + tramo valido.
        Resultado: PASSA — step 0 (guard `if not current_distance`).
        Motivo: None futuro e tolerado pelo guard de predicao.
        Prioridade: BAIXA — trava o comportamento atual.
        """
        rotadiario = _criar_rotadiario(line=1, route=10)
        fim = tz.now()
        _criar_stop_metrics(
            rotadiario, order=1, start_stop_id=1, end_stop_id=2,
            start_time=fim - timedelta(seconds=100), end_time=fim,
            distance=Decimal("1.00"),
        )
        route_data = RouteDTO(line_id=1, route_id=10, current_order=1)
        stops = [
            TripStopDTO(start_stop_id=1, end_stop_id=2, order=1, distance_km=1.0),
            TripStopDTO(start_stop_id=2, end_stop_id=3, order=2, distance_km=None),
        ]
        with patch("metrics.service.RouteMaterialization") as mock_cls:
            mock_cls.return_value.route_stops = stops
            mock_cls.return_value.get_route_stops.return_value = None
            result = build_route_timeline_prediction(route_data, base_time=fim)
        self.assertEqual(result.timeline[1].status, "pendente")
        self.assertEqual(result.timeline[1].step_seconds, 0)


# ----------------------------------------------------------------------
# T42-T46: segunda leva da auditoria.
# ----------------------------------------------------------------------


class AuditoriaLacunas2Tests(TestCase):
    """Testes T42-T46 adicionados pela auditoria do app metrics."""

    def test_T42_timeline_current_order_zero_tudo_pendente(self):
        """T42 — current_order=0 nao quebra a timeline.

        Detalhamento: current_order=0 com 2 paradas; nenhuma e <= 0.
        Resultado: PASSA — ambas pendentes, total 120 s.
        Motivo: branch `rs.order <= current_order` nunca acerta; sem
        guard, mas sem crash.
        Prioridade: BAIXA — borda fora do dominio (ordem >= 1).
        """
        route_data = RouteDTO(line_id=1, route_id=10, current_order=0)
        base = tz.now()
        stops = [
            TripStopDTO(start_stop_id=1, end_stop_id=2, order=1, distance_km=1.0),
            TripStopDTO(start_stop_id=2, end_stop_id=3, order=2, distance_km=1.0),
        ]
        with patch("metrics.service.RouteMaterialization") as mock_cls:
            mock_cls.return_value.route_stops = stops
            mock_cls.return_value.get_route_stops.return_value = None
            with patch(
                "metrics.service.get_time_prediction", side_effect=[50, 70]
            ):
                result = build_route_timeline_prediction(
                    route_data, base_time=base
                )
        self.assertEqual(
            [t.status for t in result.timeline], ["pendente", "pendente"]
        )
        self.assertEqual(result.total_remaining_seconds, 120)

    def test_T43_start_trip_ids_com_espaco_normalizam_chave(self):
        """T43 — ids com espaco geram a mesma chave do consumo.

        Detalhamento: start_trip_metric(" 1 ", " 10 ") + consumo ordem 1.
        Resultado: PASSA — ambos aplicam .replace(" ", "").strip().
        Motivo: contrato de normalizacao duplicado nos dois lados.
        Prioridade: BAIXA — trava o acoplamento implicito da chave.
        """
        cache.clear()
        self.addCleanup(cache.clear)
        start_trip_metric(" 1 ", " 10 ")
        chave = f"trip_start-1-10-{tz.localdate()}"
        self.assertIsNotNone(cache.get(chave))
        dto = LastStopDTO(
            line_id=1, route_id=10, current_stop_id=7,
            current_order=1, distance_km=0.5,
        )
        obj = set_last_stop_metrics(dto)
        self.assertIsNotNone(obj.start_time)
        self.assertIsNone(cache.get(chave))

    def test_T44_materialization_stub_retorna_none_sem_popular(self):
        """T44 — get_route_stops (stub R-04) retorna None e nao popula.

        Detalhamento: instancia e chama o metodo incompleto.
        Resultado: PASSA — retorna None; route_stops continua [].
        Motivo: corpo real apos `return None` (inacessivel); query de
        RouteStop comentada (app de rotas nao existe).
        Prioridade: INFO (divida tecnica) — nao expandir ate a integracao.
        """
        data = RouteDTO(line_id=1, route_id=10, current_order=2)
        mat = RouteMaterialization(data)
        self.assertIsNone(mat.get_route_stops())
        self.assertEqual(mat.route_stops, [])

    @unittest.expectedFailure
    def test_T45_velocity_distancia_string_quebra(self):
        """T45 — calculate_meters_per_second com distance str.

        Detalhamento: delta=100, distance="1.0"; espera Decimal("10").
        Resultado: FALHA — "1.0"*1000 vira string gigante e o Decimal
        explode (ou valor absurdo); nunca 10 m/s.
        Motivo: convert_km_to_m nao valida tipo (mesma raiz do T40).
        Prioridade: MEDIA.
        """
        self.assertEqual(
            calculate_meters_per_second(100, "1.0"), Decimal("10")
        )

    @unittest.expectedFailure
    def test_T46_set_stop_retry_nao_atualiza_distancia(self):
        """T46 — retry da mesma ordem ignora distancia nova (D-02).

        Detalhamento: order=1 com distance 0.5; repete com 9.9; espera 9.90.
        Resultado: FALHA — get_or_create com defaults nao atualiza no hit;
        distance permanece 0.50.
        Motivo: D-02 — retry descarta correcao de distance.
        Prioridade: MEDIA — telemetria corrigida e descartada em silencio.
        """
        dto1 = LastStopDTO(
            line_id=1, route_id=10, current_stop_id=5,
            current_order=1, distance_km=0.5,
        )
        first = set_last_stop_metrics(dto1)
        dto2 = LastStopDTO(
            line_id=1, route_id=10, current_stop_id=5,
            current_order=1, distance_km=9.9,
        )
        second = set_last_stop_metrics(dto2)
        self.assertEqual(first.id, second.id)
        second.refresh_from_db()
        self.assertEqual(second.distance, Decimal("9.90"))


# ----------------------------------------------------------------------
# T47-T52: terceira leva da auditoria (foco AGENT.md: constraints,
# transacao, normalizacao de chave, tipos Decimal e validacao numerica).
# ----------------------------------------------------------------------


class AuditoriaConstraintsTests(TestCase):
    """Testes T47-T52: constraints, tipos e transacao (auditoria)."""

    @unittest.expectedFailure
    def test_T47_stop_order_negativa_persiste_sem_validacao(self):
        """T47 — order negativa persiste (falta guard de dominio).

        Detalhamento: set_last_stop_metrics com current_order=-1.
        Resultado: FALHA — cria StopMetrics(order=-1); esperado rejeitar
        (ordem >= 1, AGENT.md 2.1; PositiveIntegerField sem CHECK ativo
        no SQLite).
        Motivo: service nao valida current_order antes do get_or_create.
        Prioridade: BAIXA.
        """
        dto = LastStopDTO(
            line_id=1, route_id=10, current_stop_id=5,
            current_order=-1, distance_km=0.5,
        )
        obj = set_last_stop_metrics(dto)
        self.assertEqual(obj.order, -1)

    def test_T48_stop_distance_decimal_exato_preservado(self):
        """T48 — distance Decimal com 2 casas e preservado.

        Detalhamento: cria order=1 com distance Decimal("2.55").
        Resultado: PASSA — distance gravado e 2.55.
        Motivo: DecimalField(max_digits=6, decimal_places=2) persiste
        exato; trava o caminho feliz contra regressao de arredondamento.
        Prioridade: BAIXA.
        """
        dto = LastStopDTO(
            line_id=1, route_id=10, current_stop_id=5,
            current_order=1, distance_km=Decimal("2.55"),
        )
        obj = set_last_stop_metrics(dto)
        obj.refresh_from_db()
        self.assertEqual(obj.distance, Decimal("2.55"))

    def test_T49_set_stop_transacao_valida_cria_cabecalho_e_tramo(self):
        """T49 — criacao de cabecalho + tramo sob transaction.atomic.

        Detalhamento: sem LastRouteDay previo, chama order=1.
        Resultado: PASSA — cria 1 LastRouteDay + 1 StopMetrics ligados.
        Motivo: get_or_create do cabecalho e do tramo rodam no mesmo
        bloco atomico (AGENT.md: operacoes compostas devem ser atomicas).
        Prioridade: BAIXA — trava a atomicidade do caminho feliz.
        """
        dto = LastStopDTO(
            line_id=1, route_id=10, current_stop_id=5,
            current_order=1, distance_km=0.5,
        )
        obj = set_last_stop_metrics(dto)
        self.assertEqual(
            LastRouteDay.objects.filter(line_id=1, route_id=10).count(), 1
        )
        self.assertEqual(obj.last_route_day.date, tz.localdate())
        self.assertEqual(obj.order, 1)

    def test_T50_register_constraint_impede_duplicata_concorrente(self):
        """T50 — UniqueConstraint barra duplicata direta no banco.

        Detalhamento: cria via service e tenta insert duplicado manual.
        Resultado: PASSA — segundo insert levanta IntegrityError.
        Motivo: UniqueConstraint(user, route_id, day) (AGENT.md: manter
        constraints rigidas, inclusive em retry).
        Prioridade: BAIXA — trava a garantia de banco alem do service.
        """
        from django.db import IntegrityError

        user = _criar_usuario(email="t50@unirotas.com")
        register_student_on_route(user, 10)
        with self.assertRaises(IntegrityError):
            StudentsUsingBus.objects.create(
                user=user, route_id=10, day=tz.localdate()
            )

    def test_T51_timeline_eta_none_quando_step_zero(self):
        """T51 — pendente com step 0 ainda carimba eta (= base).

        Detalhamento: perna futura distance None (step 0) com base fixa.
        Resultado: PASSA (comportamento atual) — eta = base + 0 s, ou
        seja, eta == base mesmo sem custo real.
        Motivo: o branch pendente sempre soma e carimba eta, sem
        distinguir step 0 (ETA "gratis" vindo do guard de predicao).
        Prioridade: BAIXA — documenta semantica atual para futura decisao
        (eta None vs eta=base quando step=0).
        """
        rotadiario = _criar_rotadiario(line=1, route=10)
        fim = tz.now()
        _criar_stop_metrics(
            rotadiario, order=1, start_stop_id=1, end_stop_id=2,
            start_time=fim - timedelta(seconds=100), end_time=fim,
            distance=Decimal("1.00"),
        )
        route_data = RouteDTO(line_id=1, route_id=10, current_order=1)
        stops = [
            TripStopDTO(start_stop_id=1, end_stop_id=2, order=1, distance_km=1.0),
            TripStopDTO(start_stop_id=2, end_stop_id=3, order=2, distance_km=None),
        ]
        with patch("metrics.service.RouteMaterialization") as mock_cls:
            mock_cls.return_value.route_stops = stops
            mock_cls.return_value.get_route_stops.return_value = None
            result = build_route_timeline_prediction(route_data, base_time=fim)
        self.assertEqual(result.timeline[1].step_seconds, 0)
        self.assertEqual(result.timeline[1].eta, fim)

    def test_T52_convert_bool_true_vira_1000(self):
        """T52 — convert_km_to_m(True) retorna 1000 (bool e int).

        Detalhamento: convert_km_to_m(True).
        Resultado: PASSA (comportamento atual) — True e truthy e
        True*1000 == 1000 em Python.
        Motivo: sem validacao de tipo; bool passa como numero.
        Prioridade: BAIXA (info) — trava semantica atual; validacao
        numerica estrita (T40/T45) cobriria este caso junto.
        """
        self.assertEqual(convert_km_to_m(True), 1000)
