"""Camada de serviço do app `metrics`.

Concentra regras de negócio, orquestração de transações e cálculos
agregados (velocidade, ETA, lotação), mantendo views e models magros,
conforme as diretrizes do agent.md (seções 1, 3 e 4).
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from authentication.models import User
from .models import LastRouteDay, StopMetrics, StudentsUsingBus


def _duration_minutes(start_time, end_time) -> float:
    """Calcula Δt (em minutos) entre dois horários, sem persistir o valor."""
    start = start_time.hour * 60 + start_time.minute + start_time.second / 60
    end = end_time.hour * 60 + end_time.minute + end_time.second / 60
    return round(end - start, 1)


class RegisterRouteDayService:
    """Garante o cabeçalho de execução diário único por (line, route, date)."""

    @classmethod
    @transaction.atomic
    def execute(cls, line: str, route: str) -> LastRouteDay:
        if not line or not route:
            raise ValidationError("Os campos 'line' e 'route' são obrigatórios.")

        last_route_day, _ = LastRouteDay.objects.get_or_create(
            line=line,
            route=route,
            date=timezone.localdate(),
            defaults={
                'line': line,
                'route': route,
            }
        )
        return last_route_day


class RecordStopMetricService:
    """Registra métricas operacionais de paradas.

    A criação não gera múltiplos cabeçalhos para a mesma viagem no
    mesmo dia: o agrupamento é feito por (line, route, date), conforme
    agent.md (seção 3.1).
    """

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

        last_route_day = RegisterRouteDayService.execute(line=line, route=route)

        return StopMetrics.objects.create(
            last_route_day=last_route_day,
            start_stop=start_stop,
            end_stop=end_stop,
            start_time=start_time,
            end_time=end_time
        )


class RecordStudentUsageService:
    """Registra (de forma idempotente) o uso do transporte pelo estudante.

    A UniqueConstraint `unique_student_route_day` protege o banco contra
    duplicidade, inclusive em retries do cliente (agent.md, seção 5).
    """

    @classmethod
    @transaction.atomic
    def execute(cls, user_id: int, route: str, day=None) -> StudentsUsingBus:
        if not route:
            raise ValidationError("O campo 'route' é obrigatório.")

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise ValidationError('Usuário não encontrado.')

        day = day or timezone.localdate()

        student_usage, _ = StudentsUsingBus.objects.get_or_create(
            user=user,
            route=route,
            day=day,
        )
        return student_usage


class DailyMetricsService:
    """Indicadores operacionais agregados de um dia (visão gestor).

    Cobre o KPI de lotação (agent.md, seção 4.2) agrupando
    `StudentsUsingBus` por rota e dia.
    """

    @classmethod
    def get(cls, day=None) -> dict:
        day = day or timezone.localdate()

        route_days = (
            LastRouteDay.objects
            .filter(date=day)
            .prefetch_related('stop_metrics')
        )
        stop_metrics = (
            StopMetrics.objects
            .filter(last_route_day__date=day)
            .select_related('last_route_day')
        )

        return {
            'date': day,
            'total_routes': route_days.count(),
            'total_students': StudentsUsingBus.objects.filter(day=day).count(),
            'total_stops': stop_metrics.count(),
            'routes': [
                RouteSummaryService.serialize(route_day)
                for route_day in route_days
            ],
            'stop_metrics': [
                {
                    'id': metric.id,
                    'line': metric.line,
                    'route': metric.route,
                    'start_stop': metric.start_stop,
                    'end_stop': metric.end_stop,
                    'start_time': metric.start_time.strftime('%H:%M'),
                    'end_time': metric.end_time.strftime('%H:%M'),
                }
                for metric in stop_metrics
            ],
        }


class RouteSummaryService:
    """Resumo operacional de rota(s) por dia (tempos médios e demanda)."""

    @classmethod
    def get(cls, route_name: str, day=None) -> dict:
        day = day or timezone.localdate()

        route_day = LastRouteDay.objects.filter(route=route_name, date=day).first()
        if route_day is None:
            return {
                'exists': False,
                'route': route_name,
                'date': day,
            }
        return cls.serialize(route_day)

    @classmethod
    def get_all(cls, day=None) -> dict:
        day = day or timezone.localdate()

        route_days = (
            LastRouteDay.objects
            .filter(date=day)
            .prefetch_related('stop_metrics')
        )
        return {
            'date': day,
            'routes': [cls.serialize(route_day) for route_day in route_days],
        }

    @classmethod
    def serialize(cls, route_day: LastRouteDay) -> dict:
        stops = [
            {
                'id': metric.id,
                'start_stop': metric.start_stop,
                'end_stop': metric.end_stop,
                'start_time': metric.start_time.strftime('%H:%M'),
                'end_time': metric.end_time.strftime('%H:%M'),
                'duration_minutes': _duration_minutes(
                    metric.start_time, metric.end_time
                ),
            }
            for metric in route_day.stop_metrics.all()
        ]
        durations = [stop['duration_minutes'] for stop in stops]

        return {
            'exists': True,
            'id': route_day.id,
            'line': route_day.line,
            'route': route_day.route,
            'date': route_day.date,
            'stop_count': len(stops),
            'total_trips': len(stops),
            'total_students': StudentsUsingBus.objects.filter(
                route=route_day.route, day=route_day.date
            ).count(),
            'average_trip_time': (
                round(sum(durations) / len(durations), 1) if durations else None
            ),
            'stops': stops,
        }


class StudentUsageService:
    """Histórico de utilização do transporte por estudante."""

    @classmethod
    def get(cls, user_id: int, days: int = 7) -> dict:
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise ValidationError('Usuário não encontrado.')

        end_day = timezone.localdate()
        start_day = end_day - timedelta(days=days)
        usages = (
            StudentsUsingBus.objects
            .filter(user=user, day__gte=start_day)
            .order_by('-day')
        )

        return {
            'user': {
                'id': user.id,
                'email': user.email,
                'full_name': user.full_name,
            },
            'usage_period': {
                'start': start_day,
                'end': end_day,
            },
            'total_trips': usages.count(),
            'unique_routes': sorted({usage.route for usage in usages}),
            'trips': [
                {'route': usage.route, 'day': usage.day}
                for usage in usages
            ],
        }


class ETAService:
    """Estima o ETA de um trecho cruzando distância e histórico de execução.

    A velocidade média v = d / Δt é derivada dinamicamente a partir dos
    `StopMetrics` históricos (agent.md, seção 4.1). A distância pertence
    ao trecho entre paradas; enquanto `RotaParadas` não estiver
    integrado, ela pode ser informada opcionalmente.
    """

    @classmethod
    def estimate(
        cls,
        route: str,
        start_stop: str,
        end_stop: str,
        distance_km=None
    ) -> dict:
        metrics = StopMetrics.objects.filter(
            last_route_day__route=route,
            start_stop=start_stop,
            end_stop=end_stop,
        ).only('start_time', 'end_time')

        durations = [
            _duration_minutes(metric.start_time, metric.end_time)
            for metric in metrics
        ]

        if not durations:
            return {
                'available': False,
                'route': route,
                'start_stop': start_stop,
                'end_stop': end_stop,
                'reason': 'Sem histórico de execuções para o trecho informado.',
            }

        average_minutes = round(sum(durations) / len(durations), 1)

        estimate = {
            'available': True,
            'route': route,
            'start_stop': start_stop,
            'end_stop': end_stop,
            'samples': len(durations),
            'eta_minutes': average_minutes,
        }

        if distance_km and average_minutes > 0:
            hours = average_minutes / 60
            estimate['average_speed_kmh'] = round(float(distance_km) / hours, 2)

        return estimate

