"""
Testes automatizados da app ``metrics`` (UniRota).

O que este arquivo cobre:

    1. Servicos de escrita (services.py): RegisterRouteDayService,
       RecordStopMetricService e RecordStudentUsageService - idempotencia,
       agrupamento por (line, route, date) e validacoes.
    2. Servicos de leitura: DailyMetricsService, RouteSummaryService,
       StudentUsageService e ETAService (KPIs do agent.md, secoes 4.1 e 4.2).
    3. Views de template (dashboard, detalhe de rota, rotas, historico).
    4. API JSON (registro e consulta) incluindo autenticacao e CSRF.

Como rodar:

    python manage.py test metrics -v 2
"""
import json
from datetime import time, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from authentication.models import User
from .models import LastRouteDay, StopMetrics, StudentsUsingBus
from .services import (
    DailyMetricsService,
    ETAService,
    RecordStopMetricService,
    RecordStudentUsageService,
    RegisterRouteDayService,
    RouteSummaryService,
    StudentUsageService,
)

# O fluxo de testes cria usuarios e valida senhas; MD5 mantem a bateria rapida
# (mesma estrategia adotada em authentication/tests.py).
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

SENHA_FORTE = "Senha@123"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def criar_usuario(email="aluno@unirotas.com", password=SENHA_FORTE, **extra):
    """Cria um usuario direto pelo manager (bypassa os formularios)."""
    extra.setdefault("full_name", "Usuario de Teste")
    return User.objects.create_user(email=email, password=password, **extra)


def criar_metrica(
    line="Linha 1",
    route="Rota Centro",
    start_stop="Terminal",
    end_stop="Campus",
    start_time=time(7, 0),
    end_time=time(7, 35),
):
    """Cria uma metrica de parada via service."""
    return RecordStopMetricService.execute(
        line=line,
        route=route,
        start_stop=start_stop,
        end_stop=end_stop,
        start_time=start_time,
        end_time=end_time,
    )


# ---------------------------------------------------------------------------
# 1. Servicos de escrita
# ---------------------------------------------------------------------------
class RegisterRouteDayServiceTests(TestCase):
    """O cabecalho de execucao deve ser unico por (line, route, date)."""

    def test_cria_cabecalho_do_dia(self):
        cabecalho = RegisterRouteDayService.execute("Linha 1", "Rota Centro")

        self.assertEqual(cabecalho.line, "Linha 1")
        self.assertEqual(cabecalho.route, "Rota Centro")
        self.assertEqual(cabecalho.date, timezone.localdate())
        self.assertEqual(LastRouteDay.objects.count(), 1)

    def test_reaproveita_cabecalho_em_chamadas_repetidas(self):
        primeiro = RegisterRouteDayService.execute("Linha 1", "Rota Centro")
        segundo = RegisterRouteDayService.execute("Linha 1", "Rota Centro")

        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(LastRouteDay.objects.count(), 1)

    def test_exige_line_e_route(self):
        with self.assertRaises(ValidationError):
            RegisterRouteDayService.execute("", "Rota Centro")


class RecordStopMetricServiceTests(TestCase):
    """A metrica de parada deve validar horarios e reutilizar o cabecalho."""

    def test_registra_metrica_e_expoe_line_route_via_property(self):
        metrica = criar_metrica()

        self.assertEqual(StopMetrics.objects.count(), 1)
        self.assertEqual(metrica.start_stop, "Terminal")
        self.assertEqual(metrica.end_stop, "Campus")
        self.assertEqual(metrica.line, "Linha 1")
        self.assertEqual(metrica.route, "Rota Centro")

    def test_nao_cria_multiplos_cabecalhos_para_a_mesma_viagem(self):
        criar_metrica(start_time=time(7, 0), end_time=time(7, 35))
        criar_metrica(
            start_stop="Campus",
            end_stop="Terminal",
            start_time=time(8, 0),
            end_time=time(8, 40),
        )

        self.assertEqual(LastRouteDay.objects.count(), 1)
        self.assertEqual(StopMetrics.objects.count(), 2)

    def test_rejeita_chegada_anterior_a_partida(self):
        with self.assertRaises(ValidationError):
            criar_metrica(start_time=time(8, 0), end_time=time(7, 0))

        self.assertEqual(StopMetrics.objects.count(), 0)



class RecordStudentUsageServiceTests(TestCase):
    """O registro de presenca deve ser idempotente por (user, route, day)."""

    def setUp(self):
        self.aluno = criar_usuario()

    def test_registra_presenca(self):
        uso = RecordStudentUsageService.execute(self.aluno.id, "Rota Centro")

        self.assertEqual(uso.user, self.aluno)
        self.assertEqual(uso.route, "Rota Centro")
        self.assertEqual(uso.day, timezone.localdate())

    def test_repeticao_nao_duplica_registro(self):
        primeiro = RecordStudentUsageService.execute(self.aluno.id, "Rota Centro")
        segundo = RecordStudentUsageService.execute(self.aluno.id, "Rota Centro")

        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(StudentsUsingBus.objects.count(), 1)

    def test_constraint_do_banco_bloqueia_duplicidade(self):
        RecordStudentUsageService.execute(self.aluno.id, "Rota Centro")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StudentsUsingBus.objects.create(
                    user=self.aluno,
                    route="Rota Centro",
                    day=timezone.localdate(),
                )

    def test_usuario_inexistente(self):
        with self.assertRaises(ValidationError):
            RecordStudentUsageService.execute(99999, "Rota Centro")

    def test_aceita_data_explicita(self):
        ontem = timezone.localdate() - timedelta(days=1)

        uso = RecordStudentUsageService.execute(
            self.aluno.id, "Rota Centro", day=ontem
        )

        self.assertEqual(uso.day, ontem)


# ---------------------------------------------------------------------------
# 2. Servicos de leitura
# ---------------------------------------------------------------------------
class DailyMetricsServiceTests(TestCase):
    """Os indicadores do dia devem agregar rotas, alunos e paradas."""

    def test_dia_vazio(self):
        dados = DailyMetricsService.get()

        self.assertEqual(dados["total_routes"], 0)
        self.assertEqual(dados["total_students"], 0)
        self.assertEqual(dados["total_stops"], 0)
        self.assertEqual(dados["routes"], [])

    def test_agrega_dados_do_dia(self):
        aluno = criar_usuario()
        criar_metrica()
        RecordStudentUsageService.execute(aluno.id, "Rota Centro")

        dados = DailyMetricsService.get()

        self.assertEqual(dados["date"], timezone.localdate())
        self.assertEqual(dados["total_routes"], 1)
        self.assertEqual(dados["total_students"], 1)
        self.assertEqual(dados["total_stops"], 1)
        self.assertEqual(len(dados["routes"]), 1)
        self.assertEqual(dados["routes"][0]["stop_count"], 1)
        self.assertEqual(dados["stop_metrics"][0]["route"], "Rota Centro")


class RouteSummaryServiceTests(TestCase):
    """O resumo da rota deve calcular tempos medios e demanda."""

    def test_rota_inexistente(self):
        resumo = RouteSummaryService.get("Rota Inexistente")

        self.assertFalse(resumo["exists"])

    def test_resumo_com_calculo_de_tempo_medio(self):
        criar_metrica(start_time=time(7, 0), end_time=time(7, 35))
        criar_metrica(
            start_stop="Campus",
            end_stop="Terminal",
            start_time=time(8, 0),
            end_time=time(8, 40),
        )
        aluno = criar_usuario()
        RecordStudentUsageService.execute(aluno.id, "Rota Centro")

        resumo = RouteSummaryService.get("Rota Centro")

        self.assertTrue(resumo["exists"])
        self.assertEqual(resumo["total_trips"], 2)
        self.assertEqual(resumo["stop_count"], 2)
        self.assertEqual(resumo["total_students"], 1)
        self.assertEqual(resumo["average_trip_time"], 37.5)
        self.assertEqual(len(resumo["stops"]), 2)
        self.assertEqual(resumo["stops"][0]["duration_minutes"], 35.0)

    def test_get_all_lista_rotas_do_dia(self):
        criar_metrica(route="Rota Centro")
        criar_metrica(line="Linha 2", route="Rota Norte")

        dados = RouteSummaryService.get_all()

        self.assertEqual(len(dados["routes"]), 2)



class StudentUsageServiceTests(TestCase):
    """O historico deve respeitar a janela de dias e o dono do registro."""

    def setUp(self):
        self.aluno = criar_usuario()

    def test_historico_do_aluno(self):
        ontem = timezone.localdate() - timedelta(days=1)
        RecordStudentUsageService.execute(self.aluno.id, "Rota Centro", day=ontem)
        RecordStudentUsageService.execute(self.aluno.id, "Rota Norte")

        historico = StudentUsageService.get(self.aluno.id, days=7)

        self.assertEqual(historico["total_trips"], 2)
        self.assertEqual(historico["unique_routes"], ["Rota Centro", "Rota Norte"])
        self.assertEqual(historico["user"]["email"], self.aluno.email)
        self.assertEqual(historico["trips"][0]["route"], "Rota Norte")

    def test_janela_de_dias_filtra_registros_antigos(self):
        antigo = timezone.localdate() - timedelta(days=30)
        RecordStudentUsageService.execute(self.aluno.id, "Rota Centro", day=antigo)

        historico = StudentUsageService.get(self.aluno.id, days=7)

        self.assertEqual(historico["total_trips"], 0)

    def test_usuario_inexistente(self):
        with self.assertRaises(ValidationError):
            StudentUsageService.get(99999)


class ETAServiceTests(TestCase):
    """O ETA deve ser derivado dinamicamente do historico (agent.md 4.1)."""

    def test_sem_historico_para_o_trecho(self):
        resultado = ETAService.estimate("Rota Centro", "Terminal", "Campus")

        self.assertFalse(resultado["available"])

    def test_eta_medio_e_velocidade_com_distancia(self):
        criar_metrica(start_time=time(7, 0), end_time=time(7, 35))
        criar_metrica(
            start_stop="Terminal",
            end_stop="Campus",
            start_time=time(8, 0),
            end_time=time(8, 40),
        )

        resultado = ETAService.estimate(
            "Rota Centro", "Terminal", "Campus", distance_km=15
        )

        self.assertTrue(resultado["available"])
        self.assertEqual(resultado["samples"], 2)
        self.assertEqual(resultado["eta_minutes"], 37.5)
        self.assertEqual(resultado["average_speed_kmh"], 24.0)

    def test_eta_sem_distancia_nao_inclui_velocidade(self):
        criar_metrica()

        resultado = ETAService.estimate("Rota Centro", "Terminal", "Campus")

        self.assertEqual(resultado["eta_minutes"], 35.0)
        self.assertNotIn("average_speed_kmh", resultado)


# ---------------------------------------------------------------------------
# 3. Views de template
# ---------------------------------------------------------------------------
class TemplateViewsTests(TestCase):
    """As telas do dashboard exigem autenticacao e renderizam o contexto."""

    def setUp(self):
        self.aluno = criar_usuario()
        self.client.force_login(self.aluno)

    def test_dashboard(self):
        criar_metrica()

        resposta = self.client.get(reverse("metrics:dashboard"))

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "metrics/dashboard.html")
        self.assertEqual(resposta.context["metrics"]["total_routes"], 1)
        self.assertEqual(resposta.context["today"], timezone.localdate())

    def test_route_detail(self):
        criar_metrica()

        resposta = self.client.get(
            reverse("metrics:route_detail", args=["Rota Centro"])
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "metrics/route_detail.html")
        self.assertEqual(resposta.context["route"]["total_trips"], 1)

    def test_route_detail_rota_inexistente(self):
        resposta = self.client.get(
            reverse("metrics:route_detail", args=["Rota Fantasma"])
        )

        self.assertTemplateUsed(resposta, "metrics/route_not_found.html")
        self.assertEqual(resposta.context["route_name"], "Rota Fantasma")

    def test_all_routes(self):
        criar_metrica()

        resposta = self.client.get(reverse("metrics:all_routes"))

        self.assertTemplateUsed(resposta, "metrics/all_routes.html")
        self.assertEqual(len(resposta.context["summary"]["routes"]), 1)

    def test_student_usage(self):
        RecordStudentUsageService.execute(self.aluno.id, "Rota Centro")

        resposta = self.client.get(
            reverse("metrics:student_usage", args=[self.aluno.id])
        )

        self.assertTemplateUsed(resposta, "metrics/student_usage.html")
        self.assertEqual(resposta.context["usage"]["total_trips"], 1)

    def test_student_usage_aluno_inexistente_retorna_404(self):
        resposta = self.client.get(
            reverse("metrics:student_usage", args=[99999])
        )

        self.assertEqual(resposta.status_code, 404)

    def test_views_de_template_exigem_login(self):
        visitante = Client()
        login_url = reverse("authentication:login")

        rotas = [
            reverse("metrics:dashboard"),
            reverse("metrics:all_routes"),
            reverse("metrics:route_detail", args=["Rota Centro"]),
            reverse("metrics:student_usage", args=[self.aluno.id]),
        ]

        for url in rotas:
            resposta = visitante.get(url)
            self.assertEqual(resposta.status_code, 302)
            self.assertIn(login_url, resposta.url)



# ---------------------------------------------------------------------------
# 4. API JSON
# ---------------------------------------------------------------------------
class ApiRegistroTests(TestCase):
    """Endpoints POST de registro (rota, metrica de parada e presenca)."""

    def setUp(self):
        self.aluno = criar_usuario()
        self.client.force_login(self.aluno)

    def post_json(self, url_name, payload, args=None):
        return self.client.post(
            reverse(url_name, args=args),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_register_route(self):
        resposta = self.post_json(
            "metrics:api_register_route",
            {"line": "Linha 1", "route": "Rota Centro"},
        )

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertTrue(corpo["success"])
        self.assertEqual(corpo["last_route_day"]["route"], "Rota Centro")
        self.assertEqual(LastRouteDay.objects.count(), 1)

    def test_register_route_repetida_nao_duplica_cabecalho(self):
        payload = {"line": "Linha 1", "route": "Rota Centro"}
        self.post_json("metrics:api_register_route", payload)
        resposta = self.post_json("metrics:api_register_route", payload)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(LastRouteDay.objects.count(), 1)

    def test_register_route_campos_obrigatorios(self):
        resposta = self.post_json(
            "metrics:api_register_route", {"line": "Linha 1"}
        )

        self.assertEqual(resposta.status_code, 400)
        self.assertIn("route", resposta.json()["error"])

    def test_register_route_json_invalido(self):
        resposta = self.client.post(
            reverse("metrics:api_register_route"),
            data="{nao-e-json",
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 400)

    def test_register_stop_metric(self):
        resposta = self.post_json(
            "metrics:api_register_stop_metric",
            {
                "line": "Linha 1",
                "route": "Rota Centro",
                "start_stop": "Terminal",
                "end_stop": "Campus",
                "start_time": "07:00",
                "end_time": "07:35",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertTrue(corpo["success"])
        self.assertEqual(corpo["stop_metric"]["start_time"], "07:00")
        self.assertEqual(corpo["stop_metric"]["route"], "Rota Centro")
        self.assertEqual(StopMetrics.objects.count(), 1)

    def test_register_stop_metric_horario_invalido(self):
        resposta = self.post_json(
            "metrics:api_register_stop_metric",
            {
                "line": "Linha 1",
                "route": "Rota Centro",
                "start_stop": "Terminal",
                "end_stop": "Campus",
                "start_time": "08:00",
                "end_time": "07:00",
            },
        )

        self.assertEqual(resposta.status_code, 400)
        self.assertIn("posterior", resposta.json()["error"])

    def test_register_stop_metric_formato_de_hora_invalido(self):
        resposta = self.post_json(
            "metrics:api_register_stop_metric",
            {
                "line": "Linha 1",
                "route": "Rota Centro",
                "start_stop": "Terminal",
                "end_stop": "Campus",
                "start_time": "oito da manha",
                "end_time": "07:35",
            },
        )

        self.assertEqual(resposta.status_code, 400)

    def test_record_student_bus(self):
        resposta = self.post_json(
            "metrics:api_student_bus",
            {"user_id": self.aluno.id, "route": "Rota Centro"},
        )

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["student_usage"]["user_id"], self.aluno.id)
        self.assertEqual(StudentsUsingBus.objects.count(), 1)

    def test_record_student_bus_campos_obrigatorios(self):
        resposta = self.post_json(
            "metrics:api_student_bus", {"route": "Rota Centro"}
        )

        self.assertEqual(resposta.status_code, 400)

    def test_endpoints_de_registro_exigem_login(self):
        visitante = Client()

        resposta = visitante.post(
            reverse("metrics:api_register_route"),
            data=json.dumps({"line": "L", "route": "R"}),
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 302)



class ApiConsultaTests(TestCase):
    """Endpoints GET de consulta (agregados, rota, aluno e ETA)."""

    def setUp(self):
        self.aluno = criar_usuario()
        self.client.force_login(self.aluno)

    def test_daily_metrics(self):
        criar_metrica()

        resposta = self.client.get(reverse("metrics:api_daily_metrics"))

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["total_routes"], 1)
        self.assertEqual(corpo["total_students"], 0)
        self.assertEqual(corpo["total_stops"], 1)
        self.assertEqual(corpo["date"], timezone.localdate().isoformat())

    def test_daily_metrics_data_invalida(self):
        resposta = self.client.get(
            reverse("metrics:api_daily_metrics"), {"date": "23/09/2026"}
        )

        self.assertEqual(resposta.status_code, 400)

    def test_route_summary(self):
        criar_metrica()

        resposta = self.client.get(
            reverse("metrics:api_route_summary", args=["Rota Centro"])
        )

        corpo = resposta.json()
        self.assertTrue(corpo["exists"])
        self.assertEqual(corpo["total_trips"], 1)
        self.assertEqual(corpo["average_trip_time"], 35.0)

    def test_route_summary_rota_inexistente(self):
        resposta = self.client.get(
            reverse("metrics:api_route_summary", args=["Rota Fantasma"])
        )

        corpo = resposta.json()
        self.assertFalse(corpo["exists"])

    def test_student_usage(self):
        RecordStudentUsageService.execute(self.aluno.id, "Rota Centro")

        resposta = self.client.get(
            reverse("metrics:api_student_usage", args=[self.aluno.id]),
            {"days": 30},
        )

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["total_trips"], 1)
        self.assertEqual(corpo["unique_routes"], ["Rota Centro"])

    def test_student_usage_dias_invalidos(self):
        resposta = self.client.get(
            reverse("metrics:api_student_usage", args=[self.aluno.id]),
            {"days": "muitos"},
        )

        self.assertEqual(resposta.status_code, 400)

    def test_student_usage_aluno_inexistente(self):
        resposta = self.client.get(
            reverse("metrics:api_student_usage", args=[99999])
        )

        self.assertEqual(resposta.status_code, 404)

    def test_estimate_eta(self):
        criar_metrica()

        resposta = self.client.get(
            reverse("metrics:api_estimate_eta"),
            {
                "route": "Rota Centro",
                "start_stop": "Terminal",
                "end_stop": "Campus",
                "distance_km": "14",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertTrue(corpo["available"])
        self.assertEqual(corpo["eta_minutes"], 35.0)
        self.assertEqual(corpo["average_speed_kmh"], 24.0)

    def test_estimate_eta_parametros_obrigatorios(self):
        resposta = self.client.get(
            reverse("metrics:api_estimate_eta"), {"route": "Rota Centro"}
        )

        self.assertEqual(resposta.status_code, 400)


class CsrfTests(TestCase):
    """Endpoints POST que mudam estado precisam exigir o token CSRF."""

    def test_post_sem_csrf_e_recusado(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(criar_usuario())

        resposta = csrf_client.post(
            reverse("metrics:api_register_route"),
            data=json.dumps({"line": "Linha 1", "route": "Rota Centro"}),
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(LastRouteDay.objects.count(), 0)

