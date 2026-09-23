"""Views do app `metrics`.

Recebem os dados de entrada, validam formato e delegam a regra de
negócio para a camada de serviço (`services.py`), mantendo-se magras
conforme as diretrizes do agent.md.
"""

import json
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST

from .services import (
    DailyMetricsService,
    ETAService,
    RecordStopMetricService,
    RecordStudentUsageService,
    RegisterRouteDayService,
    RouteSummaryService,
    StudentUsageService,
)


def _first_error(error: ValidationError) -> str:
    """Extrai a primeira mensagem de uma `ValidationError`."""
    messages = getattr(error, 'messages', None)
    return messages[0] if messages else str(error)


def _parse_json(request) -> dict:
    """Lê o corpo da requisição como objeto JSON."""
    try:
        payload = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValidationError('Corpo da requisição deve ser um JSON válido.')

    if not isinstance(payload, dict):
        raise ValidationError('Corpo da requisição deve ser um objeto JSON.')

    return payload


def _parse_time(value):
    """Converte 'HH:MM' ou 'HH:MM:SS' em `datetime.time`."""
    for time_format in ('%H:%M:%S', '%H:%M'):
        try:
            return datetime.strptime(value, time_format).time()
        except (TypeError, ValueError):
            continue
    raise ValidationError('Horário inválido. Utilize o formato HH:MM.')


def _parse_date(value):
    """Converte 'YYYY-MM-DD' em `datetime.date`."""
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise ValidationError('Data inválida. Utilize o formato YYYY-MM-DD.')


@login_required(login_url=reverse_lazy('authentication:login'))
def dashboard(request):
    """Dashboard com os indicadores operacionais do dia."""
    return render(request, 'metrics/dashboard.html', {
        'metrics': DailyMetricsService.get(),
        'today': timezone.localdate(),
    })


@login_required(login_url=reverse_lazy('authentication:login'))
def route_detail(request, route_name):
    """Detalhes operacionais de uma rota no dia corrente."""
    route_summary = RouteSummaryService.get(route_name)
    if not route_summary['exists']:
        return render(request, 'metrics/route_not_found.html', {
            'route_name': route_name,
        })
    return render(request, 'metrics/route_detail.html', {'route': route_summary})


@login_required(login_url=reverse_lazy('authentication:login'))
def all_routes(request):
    """Resumo de todas as rotas operadas no dia corrente."""
    return render(request, 'metrics/all_routes.html', {
        'summary': RouteSummaryService.get_all(),
    })


@login_required(login_url=reverse_lazy('authentication:login'))
def student_usage(request, user_id):
    """Histórico de utilização do transporte por estudante."""
    try:
        usage = StudentUsageService.get(user_id)
    except ValidationError as error:
        raise Http404(_first_error(error))
    return render(request, 'metrics/student_usage.html', {'usage': usage})

@login_required(login_url=reverse_lazy('authentication:login'))
@require_POST
def api_register_route(request):
    """Registra (ou garante) o cabeçalho de execução diário.

    Espera JSON: {"line": str, "route": str}
    """
    try:
        payload = _parse_json(request)
        line = payload.get('line')
        route = payload.get('route')
        if not line or not route:
            raise ValidationError("Os campos 'line' e 'route' são obrigatórios.")

        last_route_day = RegisterRouteDayService.execute(line=line, route=route)
    except ValidationError as error:
        return JsonResponse({'error': _first_error(error)}, status=400)

    return JsonResponse({
        'success': True,
        'last_route_day': {
            'id': last_route_day.id,
            'line': last_route_day.line,
            'route': last_route_day.route,
            'date': last_route_day.date,
        },
    })


@login_required(login_url=reverse_lazy('authentication:login'))
@require_POST
def api_register_stop_metric(request):
    """Registra uma métrica de parada vinculada ao cabeçalho do dia.

    Espera JSON: {"line": str, "route": str, "start_stop": str,
                  "end_stop": str, "start_time": "HH:MM", "end_time": "HH:MM"}
    """
    try:
        payload = _parse_json(request)
        line = payload.get('line')
        route = payload.get('route')
        start_stop = payload.get('start_stop')
        end_stop = payload.get('end_stop')
        if not all([line, route, start_stop, end_stop]):
            raise ValidationError(
                "Os campos 'line', 'route', 'start_stop' e 'end_stop' "
                "são obrigatórios."
            )

        start_time = _parse_time(payload.get('start_time'))
        end_time = _parse_time(payload.get('end_time'))

        metric = RecordStopMetricService.execute(
            line=line,
            route=route,
            start_stop=start_stop,
            end_stop=end_stop,
            start_time=start_time,
            end_time=end_time,
        )
    except ValidationError as error:
        return JsonResponse({'error': _first_error(error)}, status=400)

    return JsonResponse({
        'success': True,
        'stop_metric': {
            'id': metric.id,
            'line': metric.line,
            'route': metric.route,
            'start_stop': metric.start_stop,
            'end_stop': metric.end_stop,
            'start_time': metric.start_time.strftime('%H:%M'),
            'end_time': metric.end_time.strftime('%H:%M'),
        },
    })


@login_required(login_url=reverse_lazy('authentication:login'))
@require_POST
def api_record_student_bus(request):
    """Registra a presença do estudante no transporte (idempotente).

    Espera JSON: {"user_id": int, "route": str, "day": "YYYY-MM-DD"?}
    """
    try:
        payload = _parse_json(request)
        user_id = payload.get('user_id')
        route = payload.get('route')
        if not user_id or not route:
            raise ValidationError("Os campos 'user_id' e 'route' são obrigatórios.")

        day = _parse_date(payload.get('day'))

        usage = RecordStudentUsageService.execute(
            user_id=user_id, route=route, day=day
        )
    except ValidationError as error:
        return JsonResponse({'error': _first_error(error)}, status=400)

    return JsonResponse({
        'success': True,
        'student_usage': {
            'id': usage.id,
            'user_id': usage.user_id,
            'route': usage.route,
            'day': usage.day,
        },
    })


@login_required(login_url=reverse_lazy('authentication:login'))
def api_get_daily_metrics(request):
    """Retorna os indicadores agregados do dia (filtro opcional `date`)."""
    try:
        day = _parse_date(request.GET.get('date'))
    except ValidationError as error:
        return JsonResponse({'error': _first_error(error)}, status=400)

    return JsonResponse(DailyMetricsService.get(day))


@login_required(login_url=reverse_lazy('authentication:login'))
def api_get_route_summary(request, route_name):
    """Retorna o resumo operacional de uma rota (filtro opcional `date`)."""
    try:
        day = _parse_date(request.GET.get('date'))
    except ValidationError as error:
        return JsonResponse({'error': _first_error(error)}, status=400)

    return JsonResponse(RouteSummaryService.get(route_name, day))


@login_required(login_url=reverse_lazy('authentication:login'))
def api_get_student_usage(request, user_id):
    """Retorna o histórico de uso do transporte por estudante.

    Query params: `days` (janela em dias, padrão 7).
    """
    try:
        days = int(request.GET.get('days', 7))
    except (TypeError, ValueError):
        return JsonResponse(
            {'error': "O parâmetro 'days' deve ser um número inteiro."},
            status=400,
        )

    try:
        usage = StudentUsageService.get(user_id, days)
    except ValidationError as error:
        return JsonResponse({'error': _first_error(error)}, status=404)

    return JsonResponse(usage)


@login_required(login_url=reverse_lazy('authentication:login'))
def api_estimate_eta(request):
    """Estima o ETA de um trecho com base no histórico de execuções.

    Query params: `route`, `start_stop`, `end_stop` e `distance_km`
    (opcional; quando informado, retorna também a velocidade média).
    """
    route = request.GET.get('route')
    start_stop = request.GET.get('start_stop')
    end_stop = request.GET.get('end_stop')
    if not all([route, start_stop, end_stop]):
        return JsonResponse({
            'error': "Os parâmetros 'route', 'start_stop' e 'end_stop' "
                     "são obrigatórios.",
        }, status=400)

    distance_km = request.GET.get('distance_km')
    try:
        distance_km = float(distance_km) if distance_km else None
    except ValueError:
        return JsonResponse(
            {'error': "O parâmetro 'distance_km' deve ser numérico."},
            status=400,
        )

    return JsonResponse(
        ETAService.estimate(route, start_stop, end_stop, distance_km)
    )

