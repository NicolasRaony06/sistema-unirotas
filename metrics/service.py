from .models import StudentsUsingBus, StopMetrics, LastRouteDay
import math
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
from .data_type import LastStopDTO, RoutePredictionDTO, StopDTO, RouteDTO, TimeLineDTO
from .route_objects import RouteMaterialization
from authentication.models import User

def register_student_on_route(user: User, route) -> StudentsUsingBus:
    return StudentsUsingBus.objects.get_or_create(
        user=user, 
        route_id=route, 
        day=timezone.localdate()
    )

def destruct_student_from_route(user:User, route) -> bool:
    student = StudentsUsingBus.objects.filter(
        user=user, 
        route_id=route, 
        day=timezone.localdate()
    ).first()
    if not student:
        return False
    student.delete()
    return True

def set_route_as_done(line, route) -> bool:
    route_day = LastRouteDay.objects.filter(line_id=line, route_id=route, date=timezone.localdate()).first()
    if not route_day:
        return False

    if not route_day.is_concluded:
        route_day.is_concluded = True
        route_day.save(update_fields=['is_concluded'])
    return True

def calculate_delta_time(start: timezone.datetime, end: timezone.datetime) -> float:
    return (end - start).total_seconds()

def convert_km_to_m(distance: float) -> float:
    try:
        if distance:
            return distance * 1000
        else:
            return 0
    except:
        return 0

def calculate_meters_per_second(delta_time: timezone.datetime, distance:float) -> Decimal:
    if delta_time <= 0:
        return Decimal("0")

    meters = convert_km_to_m(distance)
    velocity = Decimal(str(meters)) / Decimal(str(delta_time))
    return velocity

def get_last_stop_metrics(line, route, current_order: int) -> StopMetrics:
    if current_order <= 1:
        return None
    last_route = LastRouteDay.objects.filter(route_id = route, line_id = line, date=timezone.localdate()).first()
    if last_route is None:
        return None
    last_order = current_order - 1
    last_stop = StopMetrics.objects.filter(last_route_day=last_route, order=last_order).first()
    return last_stop

def set_last_stop_metrics(last_stop_data: LastStopDTO) -> StopMetrics:
    now = timezone.now()
    today = timezone.localdate()
    with transaction.atomic():
        route_day, _ = LastRouteDay.objects.get_or_create(
            line_id=last_stop_data.line_id, route_id=last_stop_data.route_id, date=today
        )

        if last_stop_data.current_order == 1:
            cache_key = f"trip_start-{last_stop_data.line_id}-{last_stop_data.route_id}-{today}".replace(" ", "").strip()
            start_data = cache.get(cache_key)
            start_stop = last_stop_data.current_stop_id
            if start_data:
                start_time = start_data["start_time"]
                cache.delete(cache_key)
            else:
                start_time = now
        else:
            last_stop = get_last_stop_metrics(last_stop_data.line_id, last_stop_data.route_id, last_stop_data.current_order)
            if not last_stop:
                start_stop = last_stop_data.current_stop_id
                start_time = now
            else:
                start_stop = last_stop.end_stop_id
                start_time = last_stop.end_time

        if start_time > now:
            raise ValueError("O horário inicial não pode ser posterior ao horário final.")

        new_stop, _ = StopMetrics.objects.get_or_create(
            last_route_day= route_day,
            order= last_stop_data.current_order,
            defaults={
                'start_stop_id': start_stop,
                'end_stop_id': last_stop_data.current_stop_id,
                'start_time': start_time,
                'end_time': now,
                'distance': last_stop_data.distance_km,
            }
        )
        return new_stop

def get_time_prediction(stop_data: StopDTO) -> int:
    last_stop = get_last_stop_metrics(stop_data.line_id, stop_data.route_id, stop_data.order)
    if not last_stop:
        return 0
    delta_time = calculate_delta_time(last_stop.start_time, last_stop.end_time)
    velocity = calculate_meters_per_second(delta_time, last_stop.distance)
    current_distance = convert_km_to_m(stop_data.distance_km)
    if not current_distance or not velocity:
        return 0
    time = Decimal(str(current_distance))/Decimal(str(velocity))
    return math.ceil(time)

def start_trip_metric(line, route, ttl=28800) -> None:
    now = timezone.now()
    today = timezone.localdate()

    cache_key = f"trip_start-{line}-{route}-{today}".replace(" ", "").strip()

    cache.set(
        cache_key,
        {
            "start_time": now,
        },
        timeout=ttl,
    )


def build_route_timeline_prediction(route_data: RouteDTO, base_time:timezone.datetime = None) -> RoutePredictionDTO:
    if base_time is None:
        base_time = timezone.now()

    route = RouteMaterialization(route_data)
    route.get_route_stops()
    route_stops = route.route_stops
    timeline = []
    accumulated_seconds = 0

    for rs in route_stops:
        if rs.order <= route_data.current_order:
            status = "concluida" if rs.order < route_data.current_order else "atual"
            step_seconds = 0
            eta = None
        else:
            status = "pendente"
            step_seconds = get_time_prediction(
                StopDTO(
                line_id=route_data.line_id,
                route_id=route_data.route_id,
                order=rs.order,
                distance_km=rs.distance_km
                )
            )
            accumulated_seconds += step_seconds

            eta = base_time + timedelta(seconds=accumulated_seconds)

        timeline.append(TimeLineDTO(
            order= rs.order,
            start_stop_id= rs.start_stop_id,
            end_stop_id= rs.end_stop_id,
            status= status,
            distance_km= rs.distance_km,
            step_seconds= step_seconds,
            accumulated_seconds= accumulated_seconds,
            eta= eta
        ))

    return RoutePredictionDTO(
        current_order= route_data.current_order,
        base_time= base_time,
        total_remaining_seconds= accumulated_seconds,
        timeline= timeline
    )