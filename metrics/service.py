from .models import StudentsUsingBus, StopMetrics, LastRouteDay
import math
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from decimal import Decimal

def register_student(user, route):
    StudentsUsingBus.objects.create(user=user, route=route)

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

def get_last_stop_metrics(route, line, current_order: int):
    if current_order <= 1:
        return None
    last_route = LastRouteDay.objects.filter(route = route, line = line).first()
    last_order = current_order - 1
    last_stop = StopMetrics.objects.filter(last_route_day=last_route, order=last_order).first()
    return last_stop

def set_last_stop_metrics(line, route, current_stop, current_order: int, distance: float):
    now = timezone.now()  # Datetime completo com timezone em UTC

    with transaction.atomic():
        route_day, _ = LastRouteDay.objects.get_or_create(
            route=route, line=line, date=now.date()
        )

        if current_order == 1:
            cache_key = f"trip_start:{line}:{route}:{now.date()}"
            start_data = cache.get(cache_key)
            if start_data:
                start_stop = start_data["start_stop"]
                start_time = start_data["start_time"]
                cache.delete(cache_key)
                print(start_stop)
            else:
                start_stop = current_stop
                start_time = now
        else:
            last_stop = get_last_stop_metrics(route, line, current_order)
            start_stop = last_stop.end_stop
            start_time = last_stop.end_time

        if start_time > now:
            raise ValueError("O horário inicial não pode ser posterior ao horário final.")

        new_stop = StopMetrics.objects.create(
            last_route_day=route_day,
            start_stop=start_stop,
            end_stop=current_stop,
            start_time=start_time,
            end_time=now,
            distance=distance,
            order=current_order,
        )
        return new_stop

def get_time_prediction(line, route, order, distance):
    last_stop = get_last_stop_metrics(route, line, order)
    delta_time = calculate_delta_time(last_stop.start_time, last_stop.end_time)
    velocity = calculate_meters_per_second(delta_time, last_stop.distance)
    current_distance = convert_km_to_m(distance) #preciso pegar a distancia da ordem atual da tabela RotaParadas
    time = Decimal(str(current_distance))/Decimal(str(velocity))
    return math.ceil(time)