from dataclasses import dataclass
from typing import Optional
from django.utils import timezone

@dataclass(frozen=True)
class LastStopDTO:
    line_id: int
    route_id: int
    current_stop_id: int
    current_order: int
    distance_km: float

@dataclass(frozen=True)
class StopDTO:
    line_id: int
    route_id: int
    order: int
    distance_km: float

@dataclass(frozen=True)
class RouteDTO:
    line_id: int
    route_id: int
    current_order: int

@dataclass(frozen=True)
class TripStopDTO:
    start_stop_id: int
    end_stop_id: int
    order: int
    distance_km: float

@dataclass(frozen=True)
class TimeLineDTO:
    order: int
    start_stop_id: int
    end_stop_id: int
    status: str
    distance_km: float
    step_seconds: int
    accumulated_seconds: int
    eta: Optional[timezone.datetime] = None

@dataclass(frozen=True)
class RoutePredictionDTO:
    current_order: int
    base_time: timezone.datetime
    total_remaining_seconds: int
    timeline: list[TimeLineDTO]
