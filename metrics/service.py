from .models import StudentsUsingBus, StopMetrics, LastRouteDay
import math
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from decimal import Decimal
from datetime import timedelta

def register_student(user, route):
    return StudentsUsingBus.objects.get_or_create(
        user=user, 
        route=route, 
        day=timezone.localdate()
    )

def destruct_student(user, route):
    student = StudentsUsingBus.objects.filter(
        user=user, 
        route=route, 
        day=timezone.localdate()
    ).first()
    if not student:
        return False
    student.delete()
    return False

def set_route_as_done(line, route):
    route_day = LastRouteDay.objects.filter(line=line, route=route, date=timezone.localdate()).first()
    if not route_day:
        return False

    if not route_day.is_concluded:
        route_day.is_concluded = True
        route_day.save(update_fields=['is_concluded'])
    return True

def calculate_delta_time(start, end):
    return (end - start).total_seconds()

def convert_km_to_m(distance):
    return distance * 1000

def calculate_meters_per_second(delta_time, distance):
    if delta_time <= 0:
        return 0.0

    meters = convert_km_to_m(distance)
    velocity = Decimal(str(meters)) / Decimal(str(delta_time))
    return velocity


def calculate_next_stop_time(meters_per_second, next_stop_distance):
    if meters_per_second <= 0:
        return 0

    next_stop_meters = convert_km_to_m(next_stop_distance)
    time_remaining_seconds = math.floor(next_stop_meters / meters_per_second)
    return time_remaining_seconds

def get_last_stop_metrics(line, route, current_order: int):
    if current_order <= 1:
        return None
    last_route = LastRouteDay.objects.filter(route = route, line = line, date=timezone.localdate()).first()
    last_order = current_order - 1
    last_stop = StopMetrics.objects.filter(last_route_day=last_route, order=last_order).first()
    return last_stop

def set_last_stop_metrics(line, route, current_stop, current_order: int, distance: float):
    now = timezone.now()  # Datetime completo com timezone em UTC
    today = timezone.localdate()
    with transaction.atomic():
        route_day, _ = LastRouteDay.objects.get_or_create(
            line=line, route=route, date=today
        )

        if current_order == 1:
            cache_key = f"trip_start-{line}-{route}-{today}".replace(" ", "").strip()
            start_data = cache.get(cache_key)
            if start_data:
                start_stop = start_data["start_stop"]
                start_time = start_data["start_time"]
                cache.delete(cache_key)
            else:
                start_stop = current_stop
                start_time = now
        else:
            last_stop = get_last_stop_metrics(line, route, current_order)
            if not last_stop:
                start_stop = current_stop
                start_time = now
            else:
                start_stop = last_stop.end_stop
                start_time = last_stop.end_time

        if start_time > now:
            raise ValueError("O horário inicial não pode ser posterior ao horário final.")

        new_stop, _ = StopMetrics.objects.get_or_create(
            last_route_day=route_day,
            order=current_order,
            defaults={
                'start_stop': start_stop,
                'end_stop': current_stop,
                'start_time': start_time,
                'end_time': now,
                'distance': distance,
            }
        )
        return new_stop

def get_time_prediction(line, route, order, distance):
    last_stop = get_last_stop_metrics(line, route, order)
    if not last_stop:
        return 0
    delta_time = calculate_delta_time(last_stop.start_time, last_stop.end_time)
    velocity = calculate_meters_per_second(delta_time, last_stop.distance)
    current_distance = convert_km_to_m(distance) #preciso pegar a distancia da ordem atual da tabela RotaParadas
    if not current_distance or not velocity:
        return 0
    time = Decimal(str(current_distance))/Decimal(str(velocity))
    return math.ceil(time)

def start_trip_metric(line, route, start_stop, ttl=28800):
    now = timezone.now()
    today = timezone.localdate()

    cache_key = f"trip_start-{line}-{route}-{today}".replace(" ", "").strip()

    cache.set(
        cache_key,
        {
            "start_stop": start_stop,
            "start_time": now,
        },
        timeout=ttl,
    )


#não da para testar ainda
def build_route_timeline_prediction(line, route, current_order: int = 1, base_time=None):
    if base_time is None:
        base_time = timezone.now()

    #route_stops = RouteStop.objects.filter(route=route).select_related('start_stop', 'end_stop').order_by('order')
    route_stops = []
    timeline = []
    accumulated_seconds = 0

    for rs in route_stops:
        if rs.order <= current_order:
            status = "concluida" if rs.order < current_order else "atual"
            step_seconds = 0
            eta = None
        else:
            status = "pendente"
            step_seconds = get_time_prediction(
                line=line,
                route=route,
                order=rs.order,
                distance=rs.distance
            )
            accumulated_seconds += step_seconds

            eta = base_time + timedelta(seconds=accumulated_seconds)

        timeline.append({
            'order': rs.order,
            'start_stop': rs.start_stop.name,
            'end_stop': rs.end_stop.name,
            'status': status,
            'distance_km': rs.distance,
            'step_seconds': step_seconds,
            'accumulated_seconds': accumulated_seconds,
            'eta': eta,  # Objeto datetime nativo
        })

    return {
        'current_order': current_order,
        'base_time': base_time,
        'total_remaining_seconds': accumulated_seconds,
        'timeline': timeline
    }