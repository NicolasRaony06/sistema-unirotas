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
from management.models import TrechoViagem

def register_student_on_route(user: User, route) -> StudentsUsingBus:
    return StudentsUsingBus.objects.get_or_create(
        user=user, 
        route=route, 
        day=timezone.localdate()
    )

def destruct_student_from_route(user:User, route) -> bool:
    student = StudentsUsingBus.objects.filter(
        user=user, 
        route=route, 
        day=timezone.localdate()
    ).first()
    if not student:
        return False
    student.delete()
    return True

def set_route_as_done(line, route) -> bool:
    route_day = LastRouteDay.objects.filter(line=line, route=route, date=timezone.localdate()).first()
    if not route_day:
        return False

    if not route_day.is_concluded:
        route_day.is_concluded = True
        route_day.save(update_fields=['is_concluded'])
    return True


def cancel_stop_metric(bus_stop, route):
    route_day = LastRouteDay.objects.filter(line=route.linha, route=route, date=timezone.localdate()).first()
    with_start_stop = StopMetrics.objects.filter(start_stop=bus_stop, last_route_day=route_day).first()
    with_end_stop = StopMetrics.objects.filter(end_stop=bus_stop, last_route_day=route_day).first()
    if with_start_stop:
        with_start_stop.delete()
    if with_end_stop:
        with_end_stop.end_stop = None
        with_end_stop.save()

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


def get_last_stop_metrics(line, route) -> StopMetrics:
    last_route = LastRouteDay.objects.filter(route = route, line = line, date=timezone.localdate()).first()

    last_stop = StopMetrics.objects.filter(last_route_day=last_route).order_by("-order").first()
    return last_stop

def set_last_stop_metrics(last_stop_data: LastStopDTO) -> StopMetrics:
    now = timezone.now()
    today = timezone.localdate()
    with transaction.atomic():
        route_day, _ = LastRouteDay.objects.get_or_create(
            line=last_stop_data.line, route=last_stop_data.route, date=today
        )

        last_stop = get_last_stop_metrics(last_stop_data.line, last_stop_data.route)
        
        if not last_stop:
            stop = StopMetrics.objects.create(
                last_route_day = route_day,
                start_stop = last_stop_data.current_stop,
                start_time = now,
                order = 1
            )
            stop.save()
            return stop
        elif last_stop.end_stop is None:
            last_stop.end_stop = last_stop_data.current_stop
            last_stop.end_time = now
            trecho = TrechoViagem.objects.filter(parada_inicio=last_stop.start_stop, parada_fim=last_stop.end_stop, rota=route_day.route).first()
            if not trecho:
                return last_stop.delete()
            last_stop.distance = trecho.distancia_km
            last_stop.save()

            stop = StopMetrics.objects.create(
                            last_route_day = route_day,
                            start_stop = last_stop_data.current_stop,
                            start_time = now,
                            order = route_day.stop_metrics.count()+1
                        )
            stop.save()
            return last_stop


def get_time_prediction(stop_data: StopDTO) -> int:
    last_route = LastRouteDay.objects.filter(route = stop_data.route, line = stop_data.line, date=timezone.localdate()).first()
    last_stop = StopMetrics.objects.filter(last_route_day=last_route).exclude(end_stop=None).order_by("-order").first()
    if not last_stop:
        return 0
    delta_time = calculate_delta_time(last_stop.start_time, last_stop.end_time)
    velocity = calculate_meters_per_second(delta_time, last_stop.distance)
    current_distance = convert_km_to_m(stop_data.distance_km)
    if not current_distance or not velocity:
        return 0
    time = Decimal(str(current_distance))/Decimal(str(velocity))
    return math.ceil(time)


def build_route_timeline_prediction(route_data: RouteDTO, base_time:timezone.datetime = None) -> RoutePredictionDTO:
    last_route = LastRouteDay.objects.filter(route = route_data.route, line = route_data.line, date=timezone.localdate()).first()
    last_stop = StopMetrics.objects.filter(last_route_day=last_route).order_by("-order").exclude(end_stop=None).first()
    if not last_stop:
        return None
    current_order = last_stop.order
    if base_time is None:
        base_time = timezone.now()

    route = RouteMaterialization(route_data)
    route.get_route_stops()
    route_stops = route.route_stops
    timeline = []
    accumulated_seconds = 0

    for rs in route_stops:
        if rs.order <= current_order:
            status = "concluida" if rs.order < current_order else "concluida"
            step_seconds = 0
            eta = None
        else:
            status = "pendente"
            step_seconds = get_time_prediction(
                StopDTO(
                line=route_data.line,
                route=route_data.route,
                order=rs.order,
                distance_km=rs.distance_km
                )
            )
            accumulated_seconds += step_seconds

            eta = base_time + timedelta(seconds=accumulated_seconds)

        timeline.append(TimeLineDTO(
            order= rs.order,
            start_stop= rs.start_stop,
            end_stop= rs.end_stop,
            status= status,
            distance_km= rs.distance_km,
            step_seconds= step_seconds,
            accumulated_seconds= accumulated_seconds,
            eta= eta
        ))

    return RoutePredictionDTO(
        current_order= current_order,
        base_time= base_time,
        total_remaining_seconds= accumulated_seconds,
        timeline= timeline
    )